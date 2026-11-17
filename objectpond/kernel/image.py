import base64
import gzip
import inspect
import json
import types
import zlib
from typing import Any, Dict, List, Optional, Tuple

from .object_memory import SystemDictionary


class ImageSerializer:
    """
    Serializes and restores the complete live ObjectPond object graph:
    - SystemDictionary user-defined classes and hot-patched methods
    - ChangesLog entries and Transcript history
    - WorldMorph & full submorph hierarchy (preserving cyclic owner/submorph refs)
    - Form 32-bit pixel buffers (base64 + zlib compressed)
    - Bound method callbacks (e.g. button.on_click = window.on_accept)
    - Workspace globals (preserving shared object references with the World)
    """

    FORMAT_VERSION = "objectpond-image-1.0"
    MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024

    @classmethod
    def _safe_zlib_decompress(cls, data: bytes, wbits: int = zlib.MAX_WBITS) -> bytes:
        d = zlib.decompressobj(wbits)
        out = d.decompress(data, cls.MAX_DECOMPRESSED_BYTES + 1)
        if len(out) > cls.MAX_DECOMPRESSED_BYTES or not d.eof:
            raise ValueError("Compressed image payload exceeds maximum allowed size")
        return out

    def __init__(self, smalltalk: SystemDictionary):
        self.smalltalk = smalltalk

    def create_snapshot_dict(self, world: Any) -> Dict[str, Any]:
        obj_to_id: Dict[int, int] = {}
        objects_table: List[Dict[str, Any]] = []

        # Excluded runtime-only attributes on Morphs/Worlds that shouldn't be persisted
        transient_attrs = {
            "smalltalk",
            "_backend",
            "_canvas",
            "_transcript_listeners",
            "_drag_offset",
        }

        def encode_value(val: Any) -> Any:
            if val is None or isinstance(val, (bool, int, float, str)):
                return val

            if val is self.smalltalk:
                return {"$ref_global": "Smalltalk"}

            if isinstance(val, (list, tuple)):
                kind = "$tuple" if isinstance(val, tuple) else "$list"
                return {kind: [encode_value(item) for item in val]}

            if isinstance(val, set):
                return {"$set": [encode_value(item) for item in val]}

            if isinstance(val, dict):
                encoded_dict = {}
                for k, v in val.items():
                    if isinstance(k, str) and (k in ("Smalltalk", "World", "Transcript", "__builtins__")):
                        continue
                    if callable(v) and not isinstance(v, types.MethodType) and not hasattr(v, "__dict__"):
                        continue
                    if isinstance(v, types.ModuleType) or isinstance(v, type):
                        continue
                    encoded_dict[str(k)] = encode_value(v)
                return {"$dict": encoded_dict}

            # Bound method reference (e.g., star.boost or window.handle_accept)
            if isinstance(val, types.MethodType) and val.__self__ is not None:
                target_ref = encode_value(val.__self__)
                return {
                    "$bound_method": {
                        "self": target_ref,
                        "func": val.__func__.__name__,
                    }
                }

            # Plain function/lambda cannot be serialized as a method reference; skip gracefully
            if isinstance(val, (types.FunctionType, types.BuiltinFunctionType, types.ModuleType, type)):
                return None

            # Form bitmap or SampledSound audio object
            cls_name = val.__class__.__name__
            if cls_name == "Form" and hasattr(val, "width") and hasattr(val, "height") and hasattr(val, "pixels"):
                oid = register_object(val)
                return {"$obj": oid}
            if cls_name == "SampledSound" and hasattr(val, "samples") and hasattr(val, "sample_rate"):
                oid = register_object(val)
                return {"$obj": oid}

            # General Python / Morph instance with __dict__
            if hasattr(val, "__dict__"):
                oid = register_object(val)
                return {"$obj": oid}

            return str(val)

        def register_object(obj: Any) -> int:
            ptr = id(obj)
            if ptr in obj_to_id:
                return obj_to_id[ptr]

            oid = len(objects_table)
            obj_to_id[ptr] = oid
            cls_name = obj.__class__.__name__
            record: Dict[str, Any] = {
                "id": oid,
                "class": cls_name,
            }
            objects_table.append(record)

            if cls_name == "Form":
                raw_bytes = obj.to_bytes()
                compressed = zlib.compress(raw_bytes)
                record["form"] = {
                    "width": obj.width,
                    "height": obj.height,
                    "data": base64.b64encode(compressed).decode("ascii"),
                }
                return oid

            if cls_name == "SampledSound":
                raw_bytes = obj.to_bytes()
                compressed = zlib.compress(raw_bytes)
                record["sound"] = {
                    "sample_rate": obj.sample_rate,
                    "channels": obj.channels,
                    "data": base64.b64encode(compressed).decode("ascii"),
                }
                return oid

            obj_transient = set(transient_attrs)
            for cls in type(obj).__mro__:
                cls_t = cls.__dict__.get("_transient_attrs")
                if cls_t:
                    obj_transient.update(cls_t)
            inst_t = obj.__dict__.get("_transient_attrs")
            if inst_t:
                obj_transient.update(inst_t)

            state = {}
            for k, v in obj.__dict__.items():
                if k in obj_transient:
                    continue
                state[k] = encode_value(v)
            record["state"] = state
            return oid

        # 1. Capture user-defined classes and hot-patched methods
        user_classes = []
        modified_methods = []
        for cls_name, rec in self.smalltalk.classes.items():
            if rec.is_user_defined:
                user_classes.append({
                    "category": rec.category,
                    "name": rec.name,
                    "source": rec.class_header_source,
                    "protocols": dict(rec.protocols),
                })
            for m_name, m_src in rec.modified_methods.items():
                modified_methods.append({
                    "class": cls_name,
                    "method": m_name,
                    "protocol": rec.protocols.get(m_name, "operations"),
                    "source": m_src,
                })

        # 2. Register the root WorldMorph and workspace globals
        world_ref = encode_value(world)

        return {
            "format": self.FORMAT_VERSION,
            "user_classes": user_classes,
            "modified_methods": modified_methods,
            "changes": self.smalltalk.changes_log.to_list(),
            "transcript": list(self.smalltalk.transcript_history),
            "world": world_ref,
            "objects": objects_table,
        }

    def restore_from_snapshot_dict(self, snapshot: Dict[str, Any]) -> Any:
        # Ensure built-in morphic & tool classes are registered in self.smalltalk
        self._ensure_core_classes_registered()

        # 1. Restore ChangesLog and Transcript
        self.smalltalk.changes_log.entries = list(snapshot.get("changes", []))
        self.smalltalk.transcript_history = list(snapshot.get("transcript", []))

        # 2. Re-compile user-defined classes first
        for ucls in snapshot.get("user_classes", []):
            cls_obj = self.smalltalk.define_class(
                category=ucls["category"],
                class_source=ucls["source"],
                record_change=False,
            )
            rec = self.smalltalk.get_class_record(cls_obj.__name__)
            if rec and "protocols" in ucls:
                rec.protocols.update(ucls["protocols"])

        # 3. Re-install hot-patched methods on any classes
        for mod in snapshot.get("modified_methods", []):
            if self.smalltalk.get_class(mod["class"]) is not None:
                self.smalltalk.compile_and_install_method(
                    class_name=mod["class"],
                    method_name=mod["method"],
                    source_code=mod["source"],
                    protocol=mod.get("protocol", "operations"),
                    record_change=False,
                )

        # 4. Two-pass object graph allocation & hydration
        from objectpond.morphic.canvas import Form
        from objectpond.morphic.sound import SampledSound
        from objectpond.morphic.morph import Morph

        objects_table = snapshot.get("objects", [])
        instances: Dict[int, Any] = {}
        deferred_bound_methods: List[Tuple[Any, str, Dict[str, Any]]] = []

        # Pass 1: Allocate uninitialized shells for every object ID
        for entry in objects_table:
            oid = entry["id"]
            cls_name = entry["class"]
            if cls_name == "Form" and "form" in entry:
                finfo = entry["form"]
                raw = self._safe_zlib_decompress(base64.b64decode(finfo["data"].encode("ascii")))
                instances[oid] = Form.from_bytes(finfo["width"], finfo["height"], raw)
            elif cls_name == "SampledSound" and "sound" in entry:
                sinfo = entry["sound"]
                raw = self._safe_zlib_decompress(base64.b64decode(sinfo["data"].encode("ascii")))
                instances[oid] = SampledSound.from_bytes(
                    raw, sample_rate=sinfo.get("sample_rate", 44100), channels=sinfo.get("channels", 1)
                )
            else:
                cls_obj = self.smalltalk.get_class(cls_name)
                if cls_obj is None:
                    cls_obj = Morph
                inst = cls_obj.__new__(cls_obj)
                instances[oid] = inst

        def decode_value(val: Any) -> Any:
            if val is None or isinstance(val, (bool, int, float, str)):
                return val
            if isinstance(val, dict):
                if "$obj" in val:
                    return instances[val["$obj"]]
                if "$ref_global" in val:
                    if val["$ref_global"] == "Smalltalk":
                        return self.smalltalk
                if "$list" in val:
                    return [decode_value(x) for x in val["$list"]]
                if "$tuple" in val:
                    return tuple(decode_value(x) for x in val["$tuple"])
                if "$set" in val:
                    return set(decode_value(x) for x in val["$set"])
                if "$dict" in val:
                    return {k: decode_value(v) for k, v in val["$dict"].items()}
                if "$bound_method" in val:
                    bm = val["$bound_method"]
                    target = decode_value(bm["self"])
                    func_name = bm["func"]
                    if target is not None and hasattr(target, func_name):
                        return getattr(target, func_name)
                    return None
            return val

        # Pass 2: Populate attributes on every allocated instance
        for entry in objects_table:
            oid = entry["id"]
            if "form" in entry:
                continue
            inst = instances[oid]
            state = entry.get("state", {})
            for k, v in state.items():
                if str(k).startswith("__"):
                    continue
                if isinstance(v, dict) and "$bound_method" in v:
                    deferred_bound_methods.append((inst, k, v["$bound_method"]))
                else:
                    setattr(inst, k, decode_value(v))

        # Pass 3: Bind deferred bound methods now that all instances have their classes/attributes
        for inst, attr_name, bm in deferred_bound_methods:
            target = decode_value(bm["self"])
            func_name = bm["func"]
            if target is not None and hasattr(target, func_name):
                setattr(inst, attr_name, getattr(target, func_name))
            else:
                setattr(inst, attr_name, None)

        world = decode_value(snapshot["world"])
        if hasattr(world, "bind_smalltalk"):
            world.bind_smalltalk(self.smalltalk)
        return world

    def save_image_bytes(self, world: Any) -> bytes:
        snap = self.create_snapshot_dict(world)
        json_bytes = json.dumps(snap, separators=(",", ":")).encode("utf-8")
        return gzip.compress(json_bytes, compresslevel=6)

    @classmethod
    def parse_image_bytes(cls, data: bytes) -> Dict[str, Any]:
        if data[:2] == b"\x1f\x8b":
            json_bytes = cls._safe_zlib_decompress(data, wbits=16 + zlib.MAX_WBITS)
        else:
            if len(data) > cls.MAX_DECOMPRESSED_BYTES:
                raise ValueError("Image payload exceeds maximum allowed size")
            json_bytes = data
        snap = json.loads(json_bytes.decode("utf-8"))
        if not isinstance(snap, dict) or "objects" not in snap:
            raise ValueError("Invalid ObjectPond image snapshot")
        return snap

    def load_image_bytes(self, data: bytes) -> Any:
        snap = self.parse_image_bytes(data)
        return self.restore_from_snapshot_dict(snap)

    @staticmethod
    def list_importable_objects(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Lists top-level morphs and workspace objects available to import from a snapshot."""
        objects_by_id = {e["id"]: e for e in snapshot.get("objects", [])}
        world_ref = snapshot.get("world")
        world_oid = world_ref.get("$obj") if isinstance(world_ref, dict) else None
        world_entry = objects_by_id.get(world_oid) if world_oid is not None else None

        candidate_ids: List[int] = []
        seen = set()

        def _add_oid(oid: Optional[int]) -> None:
            if isinstance(oid, int) and oid not in seen and oid != world_oid:
                seen.add(oid)
                candidate_ids.append(oid)

        if world_entry:
            w_state = world_entry.get("state", {})
            for item in (w_state.get("submorphs") or {}).get("$list", []):
                if isinstance(item, dict) and "$obj" in item:
                    _add_oid(item["$obj"])
            for gval in (w_state.get("workspace_globals") or {}).get("$dict", {}).values():
                if isinstance(gval, dict) and "$obj" in gval:
                    _add_oid(gval["$obj"])

        # Fallback: include any remaining non-world objects if none found
        if not candidate_ids:
            for e in snapshot.get("objects", []):
                if e.get("class") not in ("WorldMorph", "HandMorph", "HaloMorph"):
                    _add_oid(e["id"])

        results: List[Dict[str, Any]] = []
        for oid in candidate_ids:
            e = objects_by_id.get(oid)
            if not e:
                continue
            cls_name = e.get("class", "Object")
            state = e.get("state", {})
            title = state.get("title")
            label_txt = state.get("label")
            detail = f"'{title}'" if isinstance(title, str) else (f"'{label_txt}'" if isinstance(label_txt, str) else "")
            if not detail and "x" in state and "y" in state:
                detail = f"({int(state.get('x', 0))}, {int(state.get('y', 0))}, {int(state.get('width', 0))}x{int(state.get('height', 0))})"
            elif "form" in e:
                f = e["form"]
                detail = f"{f.get('width', 0)}x{f.get('height', 0)} Form"
            label = f"[{oid}] {cls_name}" + (f" {detail}" if detail else "")
            results.append({"id": oid, "class": cls_name, "label": label, "entry": e})
        return results

    def import_object_from_snapshot(
        self,
        snapshot: Dict[str, Any],
        target_oid: int,
        target_world: Optional[Any] = None,
    ) -> Any:
        """Hydrates a single object (and its owned subgraph) from a snapshot into the current image."""
        self._ensure_core_classes_registered()
        objects_by_id = {e["id"]: e for e in snapshot.get("objects", [])}
        if target_oid not in objects_by_id:
            raise KeyError(f"Object ID {target_oid} not found in snapshot")

        world_ref = snapshot.get("world")
        world_oid = world_ref.get("$obj") if isinstance(world_ref, dict) else None

        # Collect reachable object IDs without traversing back into the old WorldMorph
        subgraph_ids: List[int] = []
        visited = set()

        def _collect(val: Any) -> None:
            if isinstance(val, dict):
                if "$obj" in val:
                    oid = val["$obj"]
                    if oid == world_oid or oid in visited or oid not in objects_by_id:
                        return
                    visited.add(oid)
                    subgraph_ids.append(oid)
                    entry = objects_by_id[oid]
                    for k, v in entry.get("state", {}).items():
                        if k == "owner" and isinstance(v, dict) and v.get("$obj") == world_oid:
                            continue
                        _collect(v)
                elif "$bound_method" in val:
                    _collect(val["$bound_method"].get("self"))
                else:
                    for v in val.values():
                        _collect(v)
            elif isinstance(val, list):
                for item in val:
                    _collect(item)

        _collect({"$obj": target_oid})
        needed_classes = {objects_by_id[oid]["class"] for oid in subgraph_ids}

        # Install missing user classes and their modified methods from the snapshot
        for ucls in snapshot.get("user_classes", []):
            if ucls["name"] in needed_classes or self.smalltalk.get_class(ucls["name"]) is None:
                cls_obj = self.smalltalk.define_class(
                    category=ucls["category"],
                    class_source=ucls["source"],
                    record_change=True,
                    author="import",
                )
                rec = self.smalltalk.get_class_record(cls_obj.__name__)
                if rec and "protocols" in ucls:
                    rec.protocols.update(ucls["protocols"])

        for mod in snapshot.get("modified_methods", []):
            if mod["class"] in needed_classes and self.smalltalk.get_class(mod["class"]) is not None:
                self.smalltalk.compile_and_install_method(
                    class_name=mod["class"],
                    method_name=mod["method"],
                    source_code=mod["source"],
                    protocol=mod.get("protocol", "operations"),
                    record_change=True,
                    author="import",
                )

        from objectpond.morphic.canvas import Form
        from objectpond.morphic.sound import SampledSound
        from objectpond.morphic.morph import Morph

        instances: Dict[int, Any] = {}
        deferred_bound_methods: List[Tuple[Any, str, Dict[str, Any]]] = []

        for oid in subgraph_ids:
            entry = objects_by_id[oid]
            cls_name = entry["class"]
            if cls_name == "Form" and "form" in entry:
                finfo = entry["form"]
                raw = self._safe_zlib_decompress(base64.b64decode(finfo["data"].encode("ascii")))
                instances[oid] = Form.from_bytes(finfo["width"], finfo["height"], raw)
            elif cls_name == "SampledSound" and "sound" in entry:
                sinfo = entry["sound"]
                raw = self._safe_zlib_decompress(base64.b64decode(sinfo["data"].encode("ascii")))
                instances[oid] = SampledSound.from_bytes(
                    raw, sample_rate=sinfo.get("sample_rate", 44100), channels=sinfo.get("channels", 1)
                )
            else:
                cls_obj = self.smalltalk.get_class(cls_name) or Morph
                instances[oid] = cls_obj.__new__(cls_obj)

        def decode_val(val: Any) -> Any:
            if val is None or isinstance(val, (bool, int, float, str)):
                return val
            if isinstance(val, dict):
                if "$obj" in val:
                    oid = val["$obj"]
                    if oid == world_oid:
                        return target_world
                    return instances.get(oid)
                if "$ref_global" in val and val["$ref_global"] == "Smalltalk":
                    return self.smalltalk
                if "$list" in val:
                    return [decode_val(x) for x in val["$list"]]
                if "$tuple" in val:
                    return tuple(decode_val(x) for x in val["$tuple"])
                if "$set" in val:
                    return set(decode_val(x) for x in val["$set"])
                if "$dict" in val:
                    return {k: decode_val(v) for k, v in val["$dict"].items()}
            return val

        for oid in subgraph_ids:
            entry = objects_by_id[oid]
            if "form" in entry:
                continue
            inst = instances[oid]
            for k, v in entry.get("state", {}).items():
                if str(k).startswith("__"):
                    continue
                if isinstance(v, dict) and "$bound_method" in v:
                    deferred_bound_methods.append((inst, k, v["$bound_method"]))
                else:
                    setattr(inst, k, decode_val(v))

        for inst, attr_name, bm in deferred_bound_methods:
            target = decode_val(bm["self"])
            func_name = bm["func"]
            if target is not None and hasattr(target, func_name):
                setattr(inst, attr_name, getattr(target, func_name))
            else:
                setattr(inst, attr_name, None)

        root_obj = instances[target_oid]
        if target_world is not None and isinstance(root_obj, Morph):
            root_obj.owner = None
            target_world.add_morph(root_obj)
            target_world.changed()
        return root_obj

    def _ensure_core_classes_registered(self) -> None:
        from objectpond.morphic.canvas import Form
        from objectpond.morphic.sound import SampledSound
        from objectpond.morphic.morph import Morph
        from objectpond.morphic.world import WorldMorph, HaloMorph, HandMorph
        from objectpond.morphic.widgets import (
            SystemWindowMorph,
            ButtonMorph,
            ListMorph,
            CodeEditorMorph,
            MenuMorph,
            LabelMorph,
        )

        core_map = [
            ("Morphic-Core", Form),
            ("Morphic-Core", Morph),
            ("Morphic-Core", WorldMorph),
            ("Morphic-Core", HandMorph),
            ("Morphic-Core", HaloMorph),
            ("Morphic-Widgets", SystemWindowMorph),
            ("Morphic-Widgets", ButtonMorph),
            ("Morphic-Widgets", ListMorph),
            ("Morphic-Widgets", CodeEditorMorph),
            ("Morphic-Widgets", MenuMorph),
            ("Morphic-Widgets", LabelMorph),
        ]
        for cat, cls_obj in core_map:
            if cls_obj.__name__ not in self.smalltalk.classes:
                self.smalltalk.register_class(cat, cls_obj)

        # Register optional tool classes if already imported/available
        try:
            from objectpond.morphic.app_widgets import (
                TextInputMorph,
                CheckboxMorph,
                ToggleSwitchMorph,
                SliderMorph,
                DropdownMorph,
                ProgressBarMorph,
                ImageMorph,
                TableMorph,
                TreeMorph,
                DialogMorph,
            )
            from objectpond.morphic.containers import (
                LayoutMorph,
                RowMorph,
                ColumnMorph,
                ScrollPaneMorph,
                TabViewMorph,
                SplitPaneMorph,
            )
            from objectpond.morphic.sound import SampledSound, SoundSynth, ADSR
            from objectpond.kernel.references import ExternalReference, FileReference, UrlReference
            from objectpond.morphic.connectors import ResourceIconMorph, FileMorph, UrlMorph, ConnectionArrowMorph
            from objectpond.morphic.hex_editor import HexEditorMorph
            from objectpond.morphic.markdown_editor import MarkdownEditorMorph
            from objectpond.morphic.midi_player import MidiPlayerMorph
            from objectpond.tools.browser import SystemBrowserWindow
            from objectpond.tools.workspace import WorkspaceWindow
            from objectpond.tools.inspector import InspectorWindow
            from objectpond.tools.transcript import TranscriptWindow, ChangesViewerWindow
            from objectpond.tools.app_builder import AppBuilderWindow
            from objectpond.tools.demos import BouncingAtomsMorph, BitBltPaintMorph, WidgetShowcaseWindow, SoundStudioWindow

            tool_map = [
                ("Media-Sound", SampledSound),
                ("Media-Sound", SoundSynth),
                ("Media-Sound", ADSR),
                ("Kernel-Objects", ExternalReference),
                ("Kernel-Objects", FileReference),
                ("Kernel-Objects", UrlReference),
                ("Morphic-Widgets", ResourceIconMorph),
                ("Morphic-Widgets", FileMorph),
                ("Morphic-Widgets", UrlMorph),
                ("Morphic-Widgets", ConnectionArrowMorph),
                ("Morphic-Widgets", HexEditorMorph),
                ("Morphic-Widgets", MarkdownEditorMorph),
                ("Morphic-Widgets", MidiPlayerMorph),
                ("Morphic-Widgets", TextInputMorph),
                ("Morphic-Widgets", CheckboxMorph),
                ("Morphic-Widgets", ToggleSwitchMorph),
                ("Morphic-Widgets", SliderMorph),
                ("Morphic-Widgets", DropdownMorph),
                ("Morphic-Widgets", ProgressBarMorph),
                ("Morphic-Widgets", ImageMorph),
                ("Morphic-Widgets", TableMorph),
                ("Morphic-Widgets", TreeMorph),
                ("Morphic-Widgets", DialogMorph),
                ("Morphic-Widgets", LayoutMorph),
                ("Morphic-Widgets", RowMorph),
                ("Morphic-Widgets", ColumnMorph),
                ("Morphic-Widgets", ScrollPaneMorph),
                ("Morphic-Widgets", TabViewMorph),
                ("Morphic-Widgets", SplitPaneMorph),
                ("Tools-Browser", SystemBrowserWindow),
                ("Tools-Workspace", WorkspaceWindow),
                ("Tools-Inspector", InspectorWindow),
                ("Tools-Transcript", TranscriptWindow),
                ("Tools-Transcript", ChangesViewerWindow),
                ("Tools-AppBuilder", AppBuilderWindow),
                ("User-Objects", BouncingAtomsMorph),
                ("User-Objects", BitBltPaintMorph),
                ("User-Objects", WidgetShowcaseWindow),
                ("User-Objects", SoundStudioWindow),
            ]
            for cat, cls_obj in tool_map:
                if cls_obj.__name__ not in self.smalltalk.classes:
                    self.smalltalk.register_class(cat, cls_obj)
        except ImportError:
            pass
