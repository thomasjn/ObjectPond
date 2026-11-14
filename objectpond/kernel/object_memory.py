import ast
import datetime
import gc
import inspect
import linecache
import textwrap
import traceback
from typing import Any, Callable, Dict, List, Optional, Type


class ChangesLog:
    """Smalltalk-style .changes audit log recording every class/method change and evaluation."""

    def __init__(self, entries: Optional[List[Dict[str, Any]]] = None):
        self.entries: List[Dict[str, Any]] = list(entries) if entries else []

    def record(self, kind: str, target: str, source: str, author: str = "user", protocol: str = "as yet unclassified") -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kind": kind,
            "target": target,
            "protocol": protocol,
            "author": author,
            "source": source,
        }
        self.entries.append(entry)
        return entry

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.entries)

    @classmethod
    def from_list(cls, data: List[Dict[str, Any]]) -> "ChangesLog":
        return cls(entries=data)

    def export_chunk_format(self) -> str:
        chunks = []
        for e in self.entries:
            header = f"!{e['kind']} target: {e['target']} protocol: {e['protocol']} stamp: '{e['author']} {e['timestamp']}'!"
            chunks.append(f"{header}\n{e['source']}\n!")
        return "\n\n".join(chunks)


class ClassRecord:
    """Metadata and source record for a class registered in SystemDictionary."""

    def __init__(
        self,
        name: str,
        category: str,
        cls_obj: Type[Any],
        class_source: Optional[str] = None,
        is_user_defined: bool = False,
    ):
        self.name = name
        self.category = category
        self.cls_obj = cls_obj
        self.is_user_defined = is_user_defined
        self.class_header_source = class_source or self._extract_initial_class_source(cls_obj)
        self.methods: Dict[str, str] = {}
        self.protocols: Dict[str, str] = {}
        self.modified_methods: Dict[str, str] = {}
        self._introspect_methods(cls_obj)

    def _extract_initial_class_source(self, cls_obj: Type[Any]) -> str:
        try:
            return textwrap.dedent(inspect.getsource(cls_obj))
        except Exception:
            bases = ", ".join(b.__name__ for b in cls_obj.__bases__) or "object"
            doc = cls_obj.__doc__ or f"{cls_obj.__name__} in category {self.category}"
            return f"class {cls_obj.__name__}({bases}):\n    \"\"\"{doc}\"\"\"\n"

    def _infer_protocol(self, method_name: str) -> str:
        if method_name.startswith("__") and method_name.endswith("__"):
            return "initializing"
        if "draw" in method_name or "color" in method_name or "layout" in method_name:
            return "drawing"
        if "mouse" in method_name or "key" in method_name or "click" in method_name or "handle" in method_name:
            return "events"
        if "step" in method_name:
            return "stepping"
        return "operations"

    def _introspect_methods(self, cls_obj: Type[Any]) -> None:
        # Also parse class_header_source AST if inspect.getsource fails on dynamic methods
        ast_methods: Dict[str, str] = {}
        if self.class_header_source:
            try:
                tree = ast.parse(self.class_header_source)
                lines = self.class_header_source.splitlines()
                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                start = item.lineno - 1
                                end = getattr(item, "end_lineno", start + 1)
                                snippet = "\n".join(lines[start:end])
                                ast_methods[item.name] = textwrap.dedent(snippet) + "\n"
            except Exception:
                pass

        for attr_name, val in cls_obj.__dict__.items():
            if callable(val) or isinstance(val, (classmethod, staticmethod)):
                func = val.__func__ if isinstance(val, (classmethod, staticmethod)) else val
                src = ast_methods.get(attr_name)
                if not src:
                    try:
                        src = textwrap.dedent(inspect.getsource(func))
                    except Exception:
                        try:
                            sig = str(inspect.signature(func))
                        except Exception:
                            sig = "(self, *args, **kwargs)"
                        src = f"def {attr_name}{sig}:\n    # Built-in or dynamically bound method\n    pass\n"
                self.methods[attr_name] = src
                self.protocols.setdefault(attr_name, self._infer_protocol(attr_name))


class SystemDictionary:
    """
    Global environment dictionary (`Smalltalk`) for ObjectPond.
    Manages categories, classes, method sources, hot-patching, and live instance migration.
    """

    def __init__(self, changes_log: Optional[ChangesLog] = None):
        self.changes_log = changes_log or ChangesLog()
        self.categories: Dict[str, List[str]] = {}
        self.classes: Dict[str, ClassRecord] = {}
        self.global_namespace: Dict[str, Any] = {"Smalltalk": self}
        self._transcript_listeners: List[Callable[[str], None]] = []
        self.transcript_history: List[str] = []
        self.exceptions: List[Dict[str, Any]] = []
        self._next_exception_id: int = 1
        self._populate_core_globals()

    def _populate_core_globals(self) -> None:
        import copy
        import math
        import random
        import time
        from typing import Set, Tuple, Union

        self.global_namespace.update({
            "Any": Any,
            "Callable": Callable,
            "Dict": Dict,
            "List": List,
            "Optional": Optional,
            "Set": Set,
            "Tuple": Tuple,
            "Type": Type,
            "Union": Union,
            "math": math,
            "random": random,
            "time": time,
            "copy": copy,
        })
        try:
            from objectpond.morphic.canvas import DisplayCanvas, Form
            from objectpond.morphic.morph import Morph
            from objectpond.morphic.widgets import (
                ButtonMorph,
                CodeEditorMorph,
                LabelMorph,
                ListMorph,
                MenuMorph,
                SystemWindowMorph,
            )

            self.global_namespace.setdefault("DisplayCanvas", DisplayCanvas)
            self.global_namespace.setdefault("Form", Form)
            self.global_namespace.setdefault("Morph", Morph)
            self.global_namespace.setdefault("SystemWindowMorph", SystemWindowMorph)
            self.global_namespace.setdefault("ButtonMorph", ButtonMorph)
            self.global_namespace.setdefault("ListMorph", ListMorph)
            self.global_namespace.setdefault("CodeEditorMorph", CodeEditorMorph)
            self.global_namespace.setdefault("MenuMorph", MenuMorph)
            self.global_namespace.setdefault("LabelMorph", LabelMorph)
        except ImportError:
            pass

    def log_transcript(self, message: str) -> None:
        line = str(message)
        self.transcript_history.append(line)
        for listener in list(self._transcript_listeners):
            try:
                listener(line)
            except Exception:
                pass

    def add_transcript_listener(self, callback: Callable[[str], None]) -> None:
        if callback not in self._transcript_listeners:
            self._transcript_listeners.append(callback)

    def record_exception(
        self,
        exc: BaseException,
        context: str = "",
        target: Any = None,
        max_records: int = 50,
    ) -> Dict[str, Any]:
        """Captures an exception with traceback text and per-frame locals/self for debugging."""
        exc_id = self._next_exception_id
        self._next_exception_id += 1
        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        frames: List[Dict[str, Any]] = []
        tb = exc.__traceback__
        idx = 0
        while tb is not None:
            frame = tb.tb_frame
            code = frame.f_code
            filename = code.co_filename
            lineno = tb.tb_lineno
            func_name = code.co_name
            code_line = linecache.getline(filename, lineno).strip()
            locals_repr: Dict[str, str] = {}
            sensitive_terms = ("token", "secret", "password", "passwd", "api_key", "environ")
            for k, v in frame.f_locals.items():
                ks = str(k)
                if any(term in ks.lower() for term in sensitive_terms):
                    locals_repr[ks] = "<redacted>"
                    continue
                try:
                    r = repr(v)
                    if len(r) > 200:
                        r = r[:197] + "..."
                    locals_repr[ks] = r
                except Exception:
                    locals_repr[ks] = "<unrepresentable>"

            self_obj = frame.f_locals.get("self")
            self_class = self_obj.__class__.__name__ if self_obj is not None else None
            self_repr = locals_repr.get("self")
            frames.append({
                "index": idx,
                "filename": filename,
                "lineno": lineno,
                "function": func_name,
                "code_line": code_line,
                "locals": locals_repr,
                "self_class": self_class,
                "self_repr": self_repr,
                "_self_obj": self_obj,
            })
            tb = tb.tb_next
            idx += 1

        record: Dict[str, Any] = {
            "id": exc_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "exc_type": type(exc).__name__,
            "message": str(exc),
            "context": context,
            "target_class": target.__class__.__name__ if target is not None else None,
            "target_repr": repr(target)[:200] if target is not None else None,
            "traceback_text": tb_text,
            "frames": frames,
            "_target_obj": target,
        }
        self.exceptions.append(record)
        if len(self.exceptions) > max_records:
            self.exceptions = self.exceptions[-max_records:]
        return record

    def get_exceptions(self) -> List[Dict[str, Any]]:
        """Returns summary metadata for all captured exceptions (newest last)."""
        return [
            {
                "id": e["id"],
                "timestamp": e["timestamp"],
                "exc_type": e["exc_type"],
                "message": e["message"],
                "context": e["context"],
                "target_class": e["target_class"],
                "frame_count": len(e["frames"]),
            }
            for e in self.exceptions
        ]

    def get_exception(self, exc_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Returns a captured exception record by ID, or the latest if exc_id is None."""
        if not self.exceptions:
            return None
        if exc_id is None:
            return self.exceptions[-1]
        for e in self.exceptions:
            if e["id"] == exc_id:
                return e
        return None

    def clear_exceptions(self) -> None:
        self.exceptions.clear()

    def ensure_category(self, category: str) -> None:
        if category not in self.categories:
            self.categories[category] = []

    def register_class(
        self,
        category: str,
        cls_obj: Type[Any],
        class_source: Optional[str] = None,
        is_user_defined: bool = False,
    ) -> ClassRecord:
        self.ensure_category(category)
        name = cls_obj.__name__
        if name not in self.categories[category]:
            self.categories[category].append(name)
        record = ClassRecord(
            name=name,
            category=category,
            cls_obj=cls_obj,
            class_source=class_source,
            is_user_defined=is_user_defined,
        )
        # Preserve any previously modified methods if re-registering
        if name in self.classes:
            old_rec = self.classes[name]
            for m_name, m_proto in old_rec.protocols.items():
                record.protocols.setdefault(m_name, m_proto)
        self.classes[name] = record
        self.global_namespace[name] = cls_obj
        return record

    def get_categories(self) -> List[str]:
        return list(self.categories.keys())

    def get_classes_in_category(self, category: str) -> List[str]:
        return list(self.categories.get(category, []))

    def get_class(self, class_name: str) -> Optional[Type[Any]]:
        rec = self.classes.get(class_name)
        return rec.cls_obj if rec else None

    def get_class_record(self, class_name: str) -> Optional[ClassRecord]:
        return self.classes.get(class_name)

    def get_protocols(self, class_name: str) -> List[str]:
        rec = self.classes.get(class_name)
        if not rec:
            return ["all"]
        protos = sorted(set(rec.protocols.values()))
        return ["all"] + protos

    def get_methods(self, class_name: str, protocol: str = "all") -> List[str]:
        rec = self.classes.get(class_name)
        if not rec:
            return []
        if protocol in ("all", "", None):
            return sorted(rec.methods.keys())
        return sorted(m for m, p in rec.protocols.items() if p == protocol)

    def get_method_source(self, class_name: str, method_name: str) -> str:
        rec = self.classes.get(class_name)
        if not rec:
            raise KeyError(f"Unknown class: {class_name}")
        if method_name not in rec.methods:
            raise KeyError(f"Unknown method: {class_name}.{method_name}")
        return rec.methods[method_name]

    def get_class_definition_source(self, class_name: str) -> str:
        rec = self.classes.get(class_name)
        if not rec:
            return ""
        return rec.class_header_source

    def compile_and_install_method(
        self,
        class_name: str,
        method_name: Optional[str],
        source_code: str,
        protocol: str = "operations",
        author: str = "user",
        record_change: bool = True,
    ) -> str:
        """
        Compiles Python method source code and installs it directly onto the live class
        so all existing instances immediately execute the new code.
        """
        rec = self.classes.get(class_name)
        if not rec:
            raise KeyError(f"Class '{class_name}' is not registered in SystemDictionary")

        dedented = textwrap.dedent(source_code).strip() + "\n"
        tree = ast.parse(dedented)
        func_defs = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if not func_defs:
            raise ValueError("Method source must contain a 'def <method_name>(self, ...):' definition")

        actual_name = func_defs[0].name
        env = dict(self.global_namespace)
        # Also pull in the class module's globals so imports inside the module remain accessible
        cls_module = inspect.getmodule(rec.cls_obj)
        if cls_module:
            for k, v in cls_module.__dict__.items():
                env.setdefault(k, v)
        env[class_name] = rec.cls_obj
        env["__objectpond_bases__"] = rec.cls_obj.__bases__ or (object,)

        # Compile inside a class scope so zero-arg `super()` gets a valid `__class__` cell
        indented_src = textwrap.indent(dedented, "    ")
        wrapped_src = f"class {class_name}(*__objectpond_bases__):\n{indented_src}\n"
        wrapped_tree = ast.parse(wrapped_src)

        local_ns: Dict[str, Any] = {}
        code_obj = compile(wrapped_tree, filename=f"<ObjectPond:{class_name}.{actual_name}>", mode="exec")
        exec(code_obj, env, local_ns)

        holder_cls = local_ns[class_name]
        raw_attr = holder_cls.__dict__[actual_name]
        func_obj = raw_attr.__func__ if isinstance(raw_attr, (classmethod, staticmethod)) else raw_attr
        if getattr(func_obj, "__closure__", None) and getattr(func_obj, "__code__", None):
            for var_name, cell in zip(func_obj.__code__.co_freevars, func_obj.__closure__):
                if var_name == "__class__":
                    cell.cell_contents = rec.cls_obj

        setattr(rec.cls_obj, actual_name, raw_attr)

        rec.methods[actual_name] = dedented
        rec.modified_methods[actual_name] = dedented
        rec.protocols[actual_name] = protocol or rec._infer_protocol(actual_name)
        self._sync_method_into_class_source(rec, actual_name, dedented)
        self._rebind_live_bound_methods(rec.cls_obj, actual_name)

        world = self.global_namespace.get("World")
        if world is not None and hasattr(world, "changed"):
            world.changed()

        if record_change:
            self.changes_log.record(
                kind="Method",
                target=f"{class_name}.{actual_name}",
                source=dedented,
                author=author,
                protocol=rec.protocols[actual_name],
            )
            self.log_transcript(f"Compiled {class_name}>>{actual_name} ({rec.protocols[actual_name]})")

        return actual_name

    def define_class(
        self,
        category: str,
        class_source: str,
        author: str = "user",
        record_change: bool = True,
    ) -> Type[Any]:
        """
        Compiles a full class definition, registers it in `category`, and migrates
        any existing live instances in memory to point to the new class object (`become:`).
        """
        dedented = textwrap.dedent(class_source).strip() + "\n"
        tree = ast.parse(dedented)
        class_defs = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        if not class_defs:
            raise ValueError("Source must contain a 'class <ClassName>(...):' definition")

        class_name = class_defs[0].name
        old_cls = self.get_class(class_name)

        env = dict(self.global_namespace)
        if old_cls is not None:
            cls_module = inspect.getmodule(old_cls)
            if cls_module:
                for k, v in cls_module.__dict__.items():
                    env.setdefault(k, v)
        local_ns: Dict[str, Any] = {}
        code_obj = compile(tree, filename=f"<ObjectPond:{category}/{class_name}>", mode="exec")
        exec(code_obj, env, local_ns)

        new_cls = local_ns[class_name]

        # Update original module attribute and workspace globals so new instances use new_cls
        if old_cls is not None:
            cls_module = inspect.getmodule(old_cls)
            if cls_module is not None and cls_module.__name__ != "builtins":
                try:
                    setattr(cls_module, class_name, new_cls)
                    new_cls.__module__ = cls_module.__name__
                except Exception:
                    pass

        world = self.global_namespace.get("World")
        if world is not None and hasattr(world, "workspace_globals"):
            world.workspace_globals[class_name] = new_cls

        # Migrate existing subclasses and live instances in memory (Smalltalk become:)
        if old_cls is not None and old_cls is not new_cls:
            for rec in list(self.classes.values()):
                c = rec.cls_obj
                if c is not old_cls and c is not new_cls and old_cls in getattr(c, "__bases__", ()):
                    try:
                        c.__bases__ = tuple(new_cls if b is old_cls else b for b in c.__bases__)
                    except Exception:
                        pass
            for obj in gc.get_objects():
                try:
                    if isinstance(obj, type) and obj is not old_cls and obj is not new_cls and old_cls in getattr(obj, "__bases__", ()):
                        obj.__bases__ = tuple(new_cls if b is old_cls else b for b in obj.__bases__)
                    elif type(obj) is old_cls:
                        obj.__class__ = new_cls
                except Exception:
                    pass
            if world is not None and hasattr(world, "all_morphs"):
                for m in world.all_morphs():
                    if type(m) is old_cls or m.__class__.__name__ == class_name:
                        m.__class__ = new_cls

        self.register_class(
            category=category,
            cls_obj=new_cls,
            class_source=dedented,
            is_user_defined=True,
        )

        # Rebind bound methods on live instances without resetting their __init__ state
        self._rebind_live_bound_methods(new_cls)

        if world is not None and hasattr(world, "changed"):
            world.changed()

        if record_change:
            self.changes_log.record(
                kind="Class",
                target=f"{category}.{class_name}",
                source=dedented,
                author=author,
                protocol="class-definition",
            )
            self.log_transcript(f"Defined class {class_name} in {category}")

        return new_cls

    def _rebind_live_bound_methods(
        self, cls_obj: Type[Any], method_name: Optional[str] = None
    ) -> None:
        """
        Updates any bound MethodType attributes (such as `button.on_click = window.on_accept`)
        on live objects so they point to the newly compiled method on `cls_obj`.
        """
        import types

        world = self.global_namespace.get("World")
        if world is None or not hasattr(world, "all_morphs"):
            return

        for m in world.all_morphs():
            d = getattr(m, "__dict__", None)
            if not d:
                continue
            for attr_key, attr_val in list(d.items()):
                if isinstance(attr_val, types.MethodType):
                    bound_self = attr_val.__self__
                    fn_name = attr_val.__func__.__name__
                    if bound_self is not None and isinstance(bound_self, cls_obj):
                        if method_name is None or fn_name == method_name:
                            if hasattr(bound_self, fn_name):
                                setattr(m, attr_key, getattr(bound_self, fn_name))

    def _sync_method_into_class_source(
        self, rec: ClassRecord, method_name: str, method_src: str
    ) -> None:
        """Keeps `rec.class_header_source` synchronized when an individual method is compiled."""
        indented_method = textwrap.indent(method_src.strip(), "    ")
        if not rec.class_header_source:
            return
        try:
            tree = ast.parse(rec.class_header_source)
            lines = rec.class_header_source.splitlines()
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if (
                            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and item.name == method_name
                        ):
                            start = item.lineno - 1
                            end = getattr(item, "end_lineno", start + 1)
                            new_lines = (
                                lines[:start]
                                + indented_method.splitlines()
                                + lines[end:]
                            )
                            rec.class_header_source = "\n".join(new_lines) + "\n"
                            return
                    # Method was newly added to the class; append it
                    rec.class_header_source = (
                        rec.class_header_source.rstrip() + "\n\n" + indented_method + "\n"
                    )
                    return
        except Exception:
            pass

    def _reinitialize_live_instances(self, cls_obj: Type[Any]) -> None:
        """
        Re-runs `__init__` on ALL live instances of `cls_obj` (including composite tool
        windows like SystemBrowserWindow, WorkspaceWindow, InspectorWindow, leaf Morphs,
        and non-Morph Python objects) while preserving their live position, extent,
        owner, z-order, and active user selection/focus.
        """
        world = self.global_namespace.get("World")

        if cls_obj.__name__ == "WorldMorph" and world is not None:
            saved_subs = list(world.submorphs)
            saved_globals = dict(world.workspace_globals)
            saved_cb = getattr(world, "_host_action_callback", None)
            saved_halo = world.active_halo
            saved_menu = world.active_menu
            saved_w, saved_h = world.width, world.height
            try:
                world.__init__(width=saved_w, height=saved_h, smalltalk=self)
                world.submorphs = saved_subs
                for s in saved_subs:
                    s.owner = world
                world.workspace_globals.update(saved_globals)
                world._host_action_callback = saved_cb
                world.active_halo = saved_halo
                world.active_menu = saved_menu
                world.changed()
            except Exception:
                world.submorphs = saved_subs
            return

        candidates = []
        seen_ids = set()
        if world is not None and hasattr(world, "all_morphs"):
            for m in list(world.all_morphs()):
                if (type(m) is cls_obj or isinstance(m, cls_obj)) and m is not world and id(m) not in seen_ids:
                    seen_ids.add(id(m))
                    candidates.append(m)

        for obj in gc.get_objects():
            try:
                if type(obj) is cls_obj and id(obj) not in seen_ids:
                    seen_ids.add(id(obj))
                    candidates.append(obj)
            except Exception:
                pass

        for inst in candidates:
            # 1. Non-Morph general Python objects
            if not hasattr(inst, "x") or not hasattr(inst, "submorphs"):
                try:
                    inst.__init__()
                except Exception:
                    pass
                continue

            # 2. Morph instances (both composite Windows/Tools and leaf Morphs)
            saved_x = inst.x
            saved_y = inst.y
            saved_w = inst.width
            saved_h = inst.height
            saved_owner = inst.owner
            saved_z = (
                saved_owner.submorphs.index(inst)
                if (saved_owner is not None and inst in saved_owner.submorphs)
                else None
            )
            old_submorphs = list(inst.submorphs)
            old_editor = getattr(inst, "editor", None)
            had_focus = (
                world is not None
                and hasattr(world, "hand")
                and (world.hand.keyboard_focus is inst or world.hand.keyboard_focus is old_editor)
            )

            # Capture high-level tool state so re-initialization doesn't lose user context
            browser_state = None
            if hasattr(inst, "category_list") and hasattr(inst, "selected_class_name"):
                browser_state = {
                    "category": getattr(inst, "selected_category", None),
                    "class_name": getattr(inst, "selected_class_name", None),
                    "protocol": getattr(inst, "selected_protocol", None),
                    "method_name": getattr(inst, "selected_method_name", None),
                    "text": old_editor.text if old_editor is not None else "",
                    "cursor": old_editor.cursor_idx if old_editor is not None else 0,
                    "scroll": old_editor.scroll_line if old_editor is not None else 0,
                }

            inspector_state = None
            if hasattr(inst, "target_obj") and hasattr(inst, "eval_editor"):
                inspector_state = {
                    "target_obj": getattr(inst, "target_obj", None),
                    "selected_field": getattr(inst, "selected_field", None),
                    "eval_text": inst.eval_editor.text,
                }

            widget_callbacks = {
                k: getattr(inst, k)
                for k in ("on_click", "on_select", "on_accept", "on_inspect")
                if hasattr(inst, k)
            }

            # 2a. Composite Window/Container Morphs (preserve existing child submorph instances in place)
            if len(old_submorphs) > 0:
                try:
                    proto = inst.__class__.__new__(inst.__class__)
                    self._invoke_morph_init(proto, world, saved_x, saved_y, saved_w, saved_h, inspector_state)

                    preserved_window_keys = {
                        "x",
                        "y",
                        "width",
                        "height",
                        "owner",
                        "submorphs",
                        "is_collapsed",
                        "expanded_height",
                        "selected_category",
                        "selected_class_name",
                        "selected_protocol",
                        "selected_method_name",
                        "selected_field",
                        "selected_value",
                        "_last_history_len",
                        "_last_entries_len",
                    }
                    for k, v in proto.__dict__.items():
                        if k in preserved_window_keys:
                            continue
                        if isinstance(v, (bool, int, float, str)):
                            setattr(inst, k, v)
                        elif hasattr(v, "x") and hasattr(v, "submorphs"):
                            existing_child = getattr(inst, k, None)
                            if existing_child is not None and type(existing_child) is type(v):
                                for ck in ("label", "color", "border_color", "border_width", "text_color", "corner_radius", "font"):
                                    if hasattr(v, ck):
                                        setattr(existing_child, ck, getattr(v, ck))

                    if hasattr(inst, "selected_class_name") and getattr(inst, "selected_class_name", None):
                        base = getattr(inst, "base_title", getattr(proto, "title", "System Browser"))
                        inst.title = f"{base}: {inst.selected_class_name}"

                    inst.set_bounds(saved_x, saved_y, saved_w, saved_h)
                    inst.changed()
                except Exception:
                    inst.submorphs = old_submorphs
                    inst.owner = saved_owner
                continue

            # 2b. Child Widget Submorphs inside a composite window (preserve text/items/callbacks)
            if saved_owner is not None and saved_owner is not world:
                try:
                    proto = inst.__class__.__new__(inst.__class__)
                    self._invoke_morph_init(proto, world, saved_x, saved_y, saved_w, saved_h, None)
                    for ck in ("color", "border_color", "border_width", "text_color", "corner_radius", "font"):
                        if hasattr(proto, ck):
                            setattr(inst, ck, getattr(proto, ck))
                    inst.set_bounds(saved_x, saved_y, saved_w, saved_h)
                    inst.changed()
                except Exception:
                    pass
                continue

            # 2c. Standalone/Leaf Morphs directly on the World (e.g. BouncingAtomsMorph, BitBltPaintMorph)
            try:
                inst.submorphs = []
                self._invoke_morph_init(inst, world, saved_x, saved_y, saved_w, saved_h, inspector_state)

                # Restore owner and z-order position
                inst.owner = saved_owner
                if saved_owner is not None:
                    if inst not in saved_owner.submorphs:
                        if saved_z is not None and 0 <= saved_z <= len(saved_owner.submorphs):
                            saved_owner.submorphs.insert(saved_z, inst)
                        else:
                            saved_owner.submorphs.append(inst)

                inst.set_bounds(saved_x, saved_y, saved_w, saved_h)

                # Restore widget callbacks if not set by __init__
                for k, cb in widget_callbacks.items():
                    if getattr(inst, k, None) is None and cb is not None:
                        setattr(inst, k, cb)

                if had_focus and world is not None:
                    world.hand.keyboard_focus = getattr(inst, "editor", inst)

                inst.changed()
            except Exception:
                inst.submorphs = old_submorphs
                inst.owner = saved_owner

    def _invoke_morph_init(
        self,
        inst: Any,
        world: Any,
        x: float,
        y: float,
        w: float,
        h: float,
        inspector_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        sig = inspect.signature(inst.__init__)
        params = list(sig.parameters.values())
        kwargs: Dict[str, Any] = {}
        pos_args = []

        for p in params:
            if p.name == "self":
                continue
            if p.name == "world":
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD) and not kwargs:
                    pos_args.append(world)
                else:
                    kwargs["world"] = world
            elif p.name == "target_obj" and inspector_state is not None:
                pos_args.append(inspector_state["target_obj"])
            elif p.name == "x":
                kwargs["x"] = x
            elif p.name == "y":
                kwargs["y"] = y
            elif p.name in ("width", "w"):
                kwargs[p.name] = w
            elif p.name in ("height", "h"):
                kwargs[p.name] = h
            elif p.default is inspect.Parameter.empty and p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                # Supply current attribute value if available on instance
                pos_args.append(getattr(inst, p.name, None))

        inst.__init__(*pos_args, **kwargs)
