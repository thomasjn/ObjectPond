import ast
import base64
import contextlib
import io
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from objectpond.kernel.image import ImageSerializer
from objectpond.morphic.morph import Morph
from objectpond.morphic.software_canvas import render_world_png


class ObjectPondController:
    """
    Environment-agnostic control facade over a live (SystemDictionary, WorldMorph) pair.
    Runs identically inside browser Pyodide WASM and native Python headless/test hosts.
    """

    def __init__(
        self,
        smalltalk: Any,
        world: Any,
        image_save_path: Optional[Path] = None,
    ):
        self.smalltalk = smalltalk
        self.world = world
        self.image_save_path = image_save_path
        self._id_to_obj: Dict[str, Any] = {}
        self._ptr_to_id: Dict[int, str] = {}
        self._next_obj_id: int = 1
        self._register_obj(world, preferred_id="world")

    def _register_obj(self, obj: Any, preferred_id: Optional[str] = None) -> str:
        ptr = id(obj)
        if ptr in self._ptr_to_id:
            return self._ptr_to_id[ptr]
        if preferred_id and preferred_id not in self._id_to_obj:
            oid = preferred_id
        else:
            oid = f"obj:{self._next_obj_id}"
            self._next_obj_id += 1
        self._id_to_obj[oid] = obj
        self._ptr_to_id[ptr] = oid
        return oid

    def _resolve_obj(self, object_id: Optional[str] = None, global_name: Optional[str] = None) -> Any:
        if object_id:
            if object_id == "world":
                return self.world
            if object_id in self._id_to_obj:
                return self._id_to_obj[object_id]
            raise KeyError(f"Unknown object_id '{object_id}'")
        if global_name:
            if global_name in self.world.workspace_globals:
                return self.world.workspace_globals[global_name]
            if global_name in self.smalltalk.global_namespace:
                return self.smalltalk.global_namespace[global_name]
            raise KeyError(f"Unknown global_name '{global_name}'")
        raise ValueError("Either 'object_id' or 'global_name' must be provided")

    def dispatch(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = dict(params or {})
        handlers: Dict[str, Callable[..., Any]] = {
            "status": self.op_status,
            "list_categories": self.op_list_categories,
            "list_classes": self.op_list_classes,
            "get_source": self.op_get_source,
            "define_class": self.op_define_class,
            "compile_method": self.op_compile_method,
            "evaluate": self.op_evaluate,
            "spawn_instance": self.op_spawn_instance,
            "list_morphs": self.op_list_morphs,
            "inspect_object": self.op_inspect_object,
            "mutate_object": self.op_mutate_object,
            "get_exceptions": self.op_get_exceptions,
            "get_exception_detail": self.op_get_exception_detail,
            "clear_exceptions": self.op_clear_exceptions,
            "open_debugger": self.op_open_debugger,
            "control_stepping": self.op_control_stepping,
            "mouse_event": self.op_mouse_event,
            "key_event": self.op_key_event,
            "type_text": self.op_type_text,
            "open_tool": self.op_open_tool,
            "get_transcript": self.op_get_transcript,
            "clear_transcript": self.op_clear_transcript,
            "get_changes": self.op_get_changes,
            "screenshot": self.op_screenshot,
            "save_image": self.op_save_image,
        }
        handler = handlers.get(method)
        if handler is None:
            raise ValueError(f"Unknown controller method: {method}")
        return handler(**args)

    def op_status(self) -> Dict[str, Any]:
        return {
            "width": self.world.width,
            "height": self.world.height,
            "stepping_paused": bool(getattr(self.world, "stepping_paused", False)),
            "status_message": getattr(self.world, "status_message", ""),
            "morph_count": len(self.world.all_morphs()),
            "class_count": len(self.smalltalk.classes),
            "exception_count": len(self.smalltalk.exceptions),
            "transcript_lines": len(self.smalltalk.transcript_history),
        }

    def op_list_categories(self) -> Dict[str, Any]:
        return {"categories": self.smalltalk.get_categories()}

    def op_list_classes(self, category: Optional[str] = None) -> Dict[str, Any]:
        if category:
            return {"category": category, "classes": self.smalltalk.get_classes_in_category(category)}
        by_cat = {
            cat: self.smalltalk.get_classes_in_category(cat)
            for cat in self.smalltalk.get_categories()
        }
        return {"categories": by_cat}

    def op_get_source(self, class_name: str, method_name: Optional[str] = None) -> Dict[str, Any]:
        rec = self.smalltalk.get_class_record(class_name)
        if not rec:
            raise KeyError(f"Class '{class_name}' not found")
        if method_name:
            src = self.smalltalk.get_method_source(class_name, method_name)
            if not src:
                raise KeyError(f"Method '{class_name}.{method_name}' not found")
            return {"class_name": class_name, "method_name": method_name, "source": src}
        return {
            "class_name": class_name,
            "category": rec.category,
            "methods": self.smalltalk.get_methods(class_name),
            "source": self.smalltalk.get_class_definition_source(class_name),
        }

    def op_define_class(self, category: str, source: str, author: str = "mcp") -> Dict[str, Any]:
        cls_obj = self.smalltalk.define_class(category=category, class_source=source, author=author)
        return {
            "class_name": cls_obj.__name__,
            "category": category,
            "methods": self.smalltalk.get_methods(cls_obj.__name__),
        }

    def op_compile_method(
        self,
        class_name: str,
        source: str,
        protocol: str = "operations",
        author: str = "mcp",
    ) -> Dict[str, Any]:
        method_name = self.smalltalk.compile_and_install_method(
            class_name=class_name,
            method_name=None,
            source_code=source,
            protocol=protocol,
            author=author,
        )
        return {"class_name": class_name, "method_name": method_name, "protocol": protocol}

    def op_evaluate(self, code: str) -> Dict[str, Any]:
        env = self.world.workspace_globals
        env.setdefault("World", self.world)
        env.setdefault("Smalltalk", self.smalltalk)
        buf = io.StringIO()
        result_val: Any = None
        try:
            tree = ast.parse(code, mode="exec")
            with contextlib.redirect_stdout(buf):
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    prefix = ast.Module(body=tree.body[:-1], type_ignores=[])
                    if prefix.body:
                        exec(compile(prefix, "<ObjectPond:mcp-eval>", "exec"), env, env)
                    expr = ast.Expression(body=tree.body[-1].value)
                    result_val = eval(compile(expr, "<ObjectPond:mcp-eval>", "eval"), env, env)
                else:
                    exec(compile(tree, "<ObjectPond:mcp-eval>", "exec"), env, env)
            self.world.changed()
            res_oid = self._register_obj(result_val) if hasattr(result_val, "__dict__") else None
            return {
                "ok": True,
                "result_repr": repr(result_val),
                "result_type": type(result_val).__name__,
                "result_object_id": res_oid,
                "stdout": buf.getvalue(),
            }
        except Exception as exc:
            rec = self.smalltalk.record_exception(exc, context="mcp:evaluate", target=self.world)
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "exception_id": rec["id"],
                "traceback": rec["traceback_text"],
                "stdout": buf.getvalue(),
            }

    def op_spawn_instance(
        self,
        class_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        add_to_world: bool = True,
        bind_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        cls_obj = self.smalltalk.get_class(class_name)
        if cls_obj is None:
            cls_obj = self.world.workspace_globals.get(class_name)
        if cls_obj is None:
            raise KeyError(f"Class '{class_name}' not found")

        inst = cls_obj(*(args or []), **(kwargs or {}))
        oid = self._register_obj(inst)
        if add_to_world and isinstance(inst, Morph):
            self.world.add_morph(inst)
            self.world.changed()
        if bind_name:
            self.world.workspace_globals[bind_name] = inst
        return {
            "object_id": oid,
            "class_name": inst.__class__.__name__,
            "repr": repr(inst)[:200],
            "added_to_world": bool(add_to_world and isinstance(inst, Morph)),
            "bound_name": bind_name,
        }

    def _serialize_morph(self, m: Morph, depth: int, max_depth: int) -> Dict[str, Any]:
        oid = self._register_obj(m)
        info: Dict[str, Any] = {
            "id": oid,
            "class": m.__class__.__name__,
            "x": m.x,
            "y": m.y,
            "width": m.width,
            "height": m.height,
            "visible": m.visible,
            "wants_steps": bool(m.wants_steps()),
        }
        if hasattr(m, "title"):
            info["title"] = getattr(m, "title")
        if hasattr(m, "label"):
            info["label"] = getattr(m, "label")
        if hasattr(m, "text") and isinstance(getattr(m, "text"), str):
            info["text_preview"] = getattr(m, "text")[:80]
        if depth < max_depth:
            info["submorphs"] = [
                self._serialize_morph(sub, depth + 1, max_depth) for sub in m.submorphs
            ]
        return info

    def op_list_morphs(self, max_depth: int = 6) -> Dict[str, Any]:
        return {"world": self._serialize_morph(self.world, 0, max_depth)}

    def op_inspect_object(
        self,
        object_id: Optional[str] = None,
        global_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        obj = self._resolve_obj(object_id=object_id, global_name=global_name)
        oid = self._register_obj(obj)
        fields: Dict[str, Dict[str, Any]] = {}
        if hasattr(obj, "__dict__"):
            for k, v in obj.__dict__.items():
                if str(k).startswith("__"):
                    continue
                child_id = self._register_obj(v) if hasattr(v, "__dict__") else None
                fields[str(k)] = {
                    "type": type(v).__name__,
                    "repr": repr(v)[:200],
                    "object_id": child_id,
                }
        methods = sorted(
            name for name, val in obj.__class__.__dict__.items()
            if callable(val) and not name.startswith("__")
        )
        return {
            "object_id": oid,
            "class": obj.__class__.__name__,
            "repr": repr(obj)[:200],
            "fields": fields,
            "methods": methods,
        }

    def op_mutate_object(
        self,
        attr: str,
        value_expr: str,
        object_id: Optional[str] = None,
        global_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        obj = self._resolve_obj(object_id=object_id, global_name=global_name)
        env = dict(self.world.workspace_globals)
        env["self"] = obj
        val = eval(value_expr, env, env)
        setattr(obj, attr, val)
        if hasattr(obj, "changed"):
            obj.changed()
        self.world.changed()
        return {
            "object_id": self._register_obj(obj),
            "attr": attr,
            "new_repr": repr(getattr(obj, attr))[:200],
        }

    def op_get_exceptions(self) -> Dict[str, Any]:
        return {"exceptions": self.smalltalk.get_exceptions()}

    def op_get_exception_detail(self, exc_id: Optional[int] = None) -> Dict[str, Any]:
        rec = self.smalltalk.get_exception(exc_id)
        if rec is None:
            return {"exception": None}
        frames = []
        for f in rec.get("frames", []):
            self_obj = f.get("_self_obj")
            self_oid = self._register_obj(self_obj) if self_obj is not None and hasattr(self_obj, "__dict__") else None
            frames.append({
                "index": f["index"],
                "filename": f["filename"],
                "lineno": f["lineno"],
                "function": f["function"],
                "code_line": f["code_line"],
                "locals": f["locals"],
                "self_class": f["self_class"],
                "self_repr": f["self_repr"],
                "self_object_id": self_oid,
            })
        return {
            "exception": {
                "id": rec["id"],
                "timestamp": rec["timestamp"],
                "exc_type": rec["exc_type"],
                "message": rec["message"],
                "context": rec["context"],
                "target_class": rec["target_class"],
                "target_repr": rec["target_repr"],
                "traceback_text": rec["traceback_text"],
                "frames": frames,
            }
        }

    def op_clear_exceptions(self) -> Dict[str, Any]:
        self.smalltalk.clear_exceptions()
        return {"cleared": True}

    def op_open_debugger(self, exc_id: Optional[int] = None) -> Dict[str, Any]:
        win = self.world.open_debugger(exc_id)
        self.world.changed()
        return {
            "window_id": self._register_obj(win) if win is not None else None,
            "title": getattr(win, "title", "Debugger"),
        }

    def op_control_stepping(self, action: str = "status", cycles: int = 1) -> Dict[str, Any]:
        if action == "pause":
            self.world.stepping_paused = True
        elif action == "resume":
            self.world.stepping_paused = False
        elif action == "step":
            self.world.step_n(cycles)
        elif action != "status":
            raise ValueError(f"Unknown stepping action: {action}")
        self.world.changed()
        return {
            "stepping_paused": bool(self.world.stepping_paused),
            "stepped": int(cycles) if action == "step" else 0,
        }

    def op_mouse_event(
        self,
        event_type: str,
        x: float,
        y: float,
        button: int = 0,
        alt_key: bool = False,
        shift_key: bool = False,
        delta_y: float = 0.0,
    ) -> Dict[str, Any]:
        if event_type == "down":
            self.world.handle_mouse_down(x, y, button=button, alt_key=alt_key, shift_key=shift_key)
        elif event_type == "move":
            self.world.handle_mouse_move(x, y)
        elif event_type == "up":
            self.world.handle_mouse_up(x, y, button=button)
        elif event_type == "wheel":
            self.world.handle_mouse_wheel(x, y, delta_y)
        else:
            raise ValueError(f"Unknown mouse event_type: {event_type}")
        return {"ok": True, "event_type": event_type, "x": x, "y": y}

    def op_key_event(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> Dict[str, Any]:
        self.world.handle_key_down(
            key,
            ctrl_key=ctrl_key,
            meta_key=meta_key,
            shift_key=shift_key,
            alt_key=alt_key,
        )
        return {"ok": True, "key": key}

    def op_type_text(self, text: str) -> Dict[str, Any]:
        for ch in text:
            key = "Enter" if ch == "\n" else ch
            self.world.handle_key_down(key)
        return {"ok": True, "typed_chars": len(text)}

    def op_open_tool(
        self,
        tool: str,
        target_id: Optional[str] = None,
        class_name: Optional[str] = None,
        text: Optional[str] = None,
        exc_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        win = None
        if tool == "browser":
            win = self.world.open_browser(initial_class=class_name)
        elif tool == "workspace":
            win = self.world.open_workspace(initial_text=text)
        elif tool == "inspector":
            target = self._resolve_obj(object_id=target_id) if target_id else self.world
            win = self.world.open_inspector(target)
        elif tool == "transcript":
            win = self.world.open_transcript()
        elif tool == "changes":
            win = self.world.open_changes()
        elif tool == "debugger":
            win = self.world.open_debugger(exc_id)
        elif tool == "bouncing_atoms":
            win = self.world.spawn_bouncing_atoms()
        elif tool == "bitblt_paint":
            win = self.world.spawn_bitblt_paint()
        else:
            raise ValueError(f"Unknown tool: {tool}")
        self.world.changed()
        return {
            "tool": tool,
            "window_id": self._register_obj(win) if win is not None else None,
        }

    def op_get_transcript(self, limit: int = 100) -> Dict[str, Any]:
        lines = self.smalltalk.transcript_history[-max(1, int(limit)):]
        return {"lines": lines, "total": len(self.smalltalk.transcript_history)}

    def op_clear_transcript(self) -> Dict[str, Any]:
        self.smalltalk.transcript_history.clear()
        return {"cleared": True}

    def op_get_changes(self, limit: int = 50) -> Dict[str, Any]:
        entries = self.smalltalk.changes_log.entries[-max(1, int(limit)):]
        return {"entries": entries, "total": len(self.smalltalk.changes_log.entries)}

    def op_screenshot(self) -> Dict[str, Any]:
        png_bytes = render_world_png(self.world)
        return {
            "mime_type": "image/png",
            "width": int(self.world.width),
            "height": int(self.world.height),
            "data_base64": base64.b64encode(png_bytes).decode("ascii"),
        }

    def op_save_image(self) -> Dict[str, Any]:
        serializer = ImageSerializer(self.smalltalk)
        raw = serializer.save_image_bytes(self.world)
        if self.image_save_path is not None:
            self.image_save_path.write_bytes(raw)
        elif hasattr(self.world, "trigger_host_action"):
            self.world.trigger_host_action("save_image")
        return {
            "bytes_saved": len(raw),
            "path": str(self.image_save_path) if self.image_save_path else "browser",
        }
