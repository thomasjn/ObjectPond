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

            # Form bitmap object
            cls_name = val.__class__.__name__
            if cls_name == "Form" and hasattr(val, "width") and hasattr(val, "height") and hasattr(val, "pixels"):
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

            state = {}
            for k, v in obj.__dict__.items():
                if k in transient_attrs:
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
                raw = zlib.decompress(base64.b64decode(finfo["data"].encode("ascii")))
                instances[oid] = Form.from_bytes(finfo["width"], finfo["height"], raw)
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

    def load_image_bytes(self, data: bytes) -> Any:
        try:
            json_bytes = gzip.decompress(data)
        except Exception:
            json_bytes = data
        snap = json.loads(json_bytes.decode("utf-8"))
        return self.restore_from_snapshot_dict(snap)

    def _ensure_core_classes_registered(self) -> None:
        from objectpond.morphic.canvas import Form
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
            from objectpond.tools.browser import SystemBrowserWindow
            from objectpond.tools.workspace import WorkspaceWindow
            from objectpond.tools.inspector import InspectorWindow
            from objectpond.tools.transcript import TranscriptWindow, ChangesViewerWindow
            from objectpond.tools.demos import BouncingAtomsMorph, BitBltPaintMorph

            tool_map = [
                ("Tools-Browser", SystemBrowserWindow),
                ("Tools-Workspace", WorkspaceWindow),
                ("Tools-Inspector", InspectorWindow),
                ("Tools-Transcript", TranscriptWindow),
                ("Tools-Transcript", ChangesViewerWindow),
                ("User-Objects", BouncingAtomsMorph),
                ("User-Objects", BitBltPaintMorph),
            ]
            for cat, cls_obj in tool_map:
                if cls_obj.__name__ not in self.smalltalk.classes:
                    self.smalltalk.register_class(cat, cls_obj)
        except ImportError:
            pass
