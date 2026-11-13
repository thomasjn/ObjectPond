from typing import Any, Optional
from objectpond.morphic.widgets import (
    SystemWindowMorph,
    ListMorph,
    CodeEditorMorph,
    ButtonMorph,
)


class InspectorWindow(SystemWindowMorph):
    """
    Classic Smalltalk Object Inspector.
    - Left pane: list of fields (self, __class__, instance attributes / elements)
    - Top-right pane: field value viewer + Inspect Field / Browse Class buttons
    - Bottom-right pane: interactive Python eval scratchpad bound to {"self": target_obj}
    """

    def __init__(
        self,
        world: Any,
        target_obj: Any,
        x: float = 420,
        y: float = 280,
        width: float = 480,
        height: float = 340,
    ):
        cls_name = getattr(target_obj, "__class__", type(target_obj)).__name__
        super().__init__(
            title=f"Inspector on {cls_name}",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b536e",
        )
        self.target_obj = target_obj
        self.selected_field: Optional[str] = None
        self.selected_value: Any = target_obj

        # Left pane: field list
        self.field_list = ListMorph(
            x=x + 4,
            y=y + 30,
            width=140,
            height=height - 34,
            on_select=self.on_field_selected,
        )

        # Right toolbar buttons
        self.accept_field_btn = ButtonMorph(
            "Accept (Cmd+S)",
            x=x + 148,
            y=y + 30,
            width=112,
            height=24,
            on_click=self.on_accept_field_clicked,
            color="#2d4f3e",
        )
        self.inspect_field_btn = ButtonMorph(
            "Inspect Field",
            x=x + 266,
            y=y + 30,
            width=104,
            height=24,
            on_click=self.on_inspect_field,
        )
        self.browse_class_btn = ButtonMorph(
            "Browse Class",
            x=x + 376,
            y=y + 30,
            width=100,
            height=24,
            on_click=self.on_browse_class,
        )

        eval_ctx = {"self": target_obj}

        # Right top: editable field value editor (Cmd+S or Accept button mutates the field live)
        self.value_editor = CodeEditorMorph(
            x=x + 148,
            y=y + 58,
            width=width - 152,
            height=110,
            text=repr(target_obj),
            context=eval_ctx,
            on_accept=self.on_accept_field_value,
        )

        # Right bottom: evaluation editor with context {"self": target_obj}
        self.eval_editor = CodeEditorMorph(
            x=x + 148,
            y=y + 174,
            width=width - 152,
            height=height - 178,
            text="# Evaluate expressions on `self` (Cmd+D) or edit field above (Cmd+S)\nself",
            context=eval_ctx,
            on_accept=self.on_eval_accepted,
        )

        self.add_morph(self.field_list)
        self.add_morph(self.accept_field_btn)
        self.add_morph(self.inspect_field_btn)
        self.add_morph(self.browse_class_btn)
        self.add_morph(self.value_editor)
        self.add_morph(self.eval_editor)

        self.refresh_fields()
        self.layout_submorphs()
        if self.field_list.items:
            self.field_list.select_index(0, notify=True)

    def wants_steps(self) -> bool:
        return True

    def step(self) -> None:
        # Refresh field list if attributes were added/removed on target_obj
        if hasattr(self.target_obj, "__dict__"):
            expected_count = 2 + len(
                [k for k in self.target_obj.__dict__.keys() if not k.startswith("__")]
            )
            if len(self.field_list.items) != expected_count:
                self.refresh_fields()

        # Live-refresh displayed value when user is not actively editing value_editor
        w = self.world()
        editing_value = self.value_editor.is_dirty or (
            w is not None and w.hand.keyboard_focus is self.value_editor
        )
        if not editing_value and self.selected_field is not None:
            live_val = self._resolve_field_value(self.selected_field)
            self.selected_value = live_val
            live_repr = repr(live_val)
            if self.value_editor.text != live_repr:
                self.value_editor.set_text(live_repr)

    def refresh_fields(self) -> None:
        items = ["self", "__class__"]
        if hasattr(self.target_obj, "__dict__"):
            keys = [k for k in self.target_obj.__dict__.keys() if not k.startswith("__")]
            keys.sort()
            items.extend(keys)
        elif isinstance(self.target_obj, dict):
            items.extend([f"[{repr(k)}]" for k in list(self.target_obj.keys())[:100]])
        elif isinstance(self.target_obj, (list, tuple)) and not isinstance(
            self.target_obj, (str, bytes)
        ):
            items.extend([f"[{i}]" for i in range(min(100, len(self.target_obj)))])

        self.field_list.set_items(items, keep_selection=True)

    def _resolve_field_value(self, field_name: str) -> Any:
        if field_name == "self":
            return self.target_obj
        if field_name == "__class__":
            return getattr(self.target_obj, "__class__", type(self.target_obj))
        if field_name.startswith("[") and field_name.endswith("]"):
            key_str = field_name[1:-1]
            if isinstance(self.target_obj, (list, tuple)):
                try:
                    return self.target_obj[int(key_str)]
                except Exception:
                    return None
            elif isinstance(self.target_obj, dict):
                for k in self.target_obj:
                    if repr(k) == key_str or str(k) == key_str:
                        return self.target_obj[k]
                return None
        return getattr(self.target_obj, field_name, None)

    def on_field_selected(self, idx: int, field_name: str) -> None:
        self.selected_field = field_name
        val = self._resolve_field_value(field_name)
        self.selected_value = val
        self.value_editor.set_text(repr(val))

    def on_accept_field_clicked(self) -> Any:
        return self.value_editor.accept()

    def on_eval_accepted(self, _src: Optional[str] = None) -> Any:
        res = self.eval_editor.do_it()
        self.refresh_fields()
        if self.selected_field is not None:
            self.on_field_selected(self.field_list.selected_index, self.selected_field)
        return res

    def _assign_field_value(self, field_name: str, new_val: Any) -> None:
        if field_name == "self":
            raise ValueError("Cannot reassign 'self' directly; select a field or use the eval pane")
        if field_name == "__class__":
            if not isinstance(new_val, type):
                raise TypeError("__class__ must be a class/type")
            self.target_obj.__class__ = new_val
            return
        if field_name.startswith("[") and field_name.endswith("]"):
            key_str = field_name[1:-1]
            if isinstance(self.target_obj, list):
                self.target_obj[int(key_str)] = new_val
                return
            if isinstance(self.target_obj, dict):
                for k in list(self.target_obj.keys()):
                    if repr(k) == key_str or str(k) == key_str:
                        self.target_obj[k] = new_val
                        return
                self.target_obj[key_str] = new_val
                return
            raise TypeError(f"Cannot assign indexed element on {type(self.target_obj).__name__}")

        # For Morph position/extent fields, route through set_position / set_extent so submorphs reflow
        if field_name == "x" and hasattr(self.target_obj, "set_position"):
            self.target_obj.set_position(float(new_val), getattr(self.target_obj, "y", 0.0))
        elif field_name == "y" and hasattr(self.target_obj, "set_position"):
            self.target_obj.set_position(getattr(self.target_obj, "x", 0.0), float(new_val))
        elif field_name == "width" and hasattr(self.target_obj, "set_extent"):
            self.target_obj.set_extent(float(new_val), getattr(self.target_obj, "height", 100.0))
        elif field_name == "height" and hasattr(self.target_obj, "set_extent"):
            self.target_obj.set_extent(getattr(self.target_obj, "width", 100.0), float(new_val))
        else:
            setattr(self.target_obj, field_name, new_val)

    def on_accept_field_value(self, raw_text: Optional[str] = None) -> Any:
        if raw_text is None:
            raw_text = self.value_editor.text
        expr = raw_text.strip()
        field_name = self.selected_field
        if not field_name:
            return None

        w = self.world()
        try:
            env: Dict[str, Any] = {}
            if w is not None:
                env.update(w.workspace_globals)
                env["world"] = w
            env["self"] = self.target_obj
            try:
                code_obj = compile(expr, "<inspector-field>", "eval")
                new_val = eval(code_obj, env)
            except Exception:
                # If current value is a string and user typed an unquoted literal (e.g. #ff0055), accept as str
                if isinstance(self.selected_value, str) and expr and "\n" not in expr:
                    new_val = expr
                else:
                    raise

            self._assign_field_value(field_name, new_val)
            self.selected_value = self._resolve_field_value(field_name)
            self.value_editor.set_text(repr(self.selected_value))
            self.refresh_fields()
            if hasattr(self.target_obj, "changed"):
                self.target_obj.changed()
            if w is not None:
                cls_name = getattr(self.target_obj, "__class__", type(self.target_obj)).__name__
                w.status_message = f"Updated {cls_name}.{field_name} = {repr(self.selected_value)[:40]}"
                w.changed()
            return self.selected_value
        except Exception as exc:
            if w is not None:
                w.status_message = f"Inspector update error: {exc}"
                if w.smalltalk:
                    w.smalltalk.log_transcript(f"Inspector Error ({field_name}): {exc}")
            return exc

    def on_inspect_field(self) -> None:
        val = getattr(self, "selected_value", self.target_obj)
        w = self.world()
        if w is not None:
            w.open_inspector(val)

    def on_browse_class(self) -> None:
        cls = getattr(self.target_obj, "__class__", type(self.target_obj))
        if cls is not None:
            w = self.world()
            if w is not None:
                w.open_browser(cls.__name__)

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "field_list"):
            return

        content_x = self.x + 4.0
        content_y = self.y + self.TITLEBAR_HEIGHT + 4.0
        content_w = max(100.0, self.width - 8.0)
        content_h = max(100.0, self.height - self.TITLEBAR_HEIGHT - 8.0)

        list_w = max(80.0, min(160.0, content_w * 0.30))
        self.field_list.set_bounds(content_x, content_y, list_w, content_h)

        rx = content_x + list_w + 4.0
        rw = max(60.0, content_w - list_w - 4.0)

        bx = rx
        if hasattr(self, "accept_field_btn"):
            self.accept_field_btn.set_position(bx, content_y)
            bx += self.accept_field_btn.width + 4.0
        self.inspect_field_btn.set_position(bx, content_y)
        bx += self.inspect_field_btn.width + 4.0
        self.browse_class_btn.set_position(bx, content_y)

        btn_h = 24.0
        vy = content_y + btn_h + 4.0
        vh = max(30.0, (content_h - btn_h - 8.0) * 0.44)
        self.value_editor.set_bounds(rx, vy, rw, vh)

        ey = vy + vh + 4.0
        eh = max(30.0, content_y + content_h - ey)
        self.eval_editor.set_bounds(rx, ey, rw, eh)
