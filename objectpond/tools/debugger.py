from typing import Any, Dict, List, Optional
from objectpond.morphic.widgets import (
    ButtonMorph,
    CodeEditorMorph,
    ListMorph,
    SystemWindowMorph,
)


class DebuggerWindow(SystemWindowMorph):
    """
    Live Post-Mortem & Live-Patching Debugger.
    - Top toolbar: Resume Stepping, Step Cycle, Inspect Self, Accept Fix (Cmd+S)
    - Top-left pane: stack frame list
    - Top-right pane: locals & self bindings for selected frame
    - Bottom pane: live method source (hot-patchable) or traceback view
    """

    def __init__(
        self,
        world: Any,
        exc_record: Optional[Dict[str, Any]] = None,
        x: float = 140,
        y: float = 90,
        width: float = 640,
        height: float = 440,
    ):
        if exc_record is None and world is not None and getattr(world, "smalltalk", None) is not None:
            exc_record = world.smalltalk.get_exception()

        title = "Debugger"
        if exc_record:
            title = f"Debugger: {exc_record.get('exc_type', 'Error')}: {exc_record.get('message', '')[:42]}"

        super().__init__(
            title=title,
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#6b2d38",
        )
        self._world_ref = world
        self.exc_id: Optional[int] = exc_record.get("id") if exc_record else None
        self.exc_record: Optional[Dict[str, Any]] = exc_record
        self.selected_frame_idx: int = 0
        self._editing_class: Optional[str] = None
        self._editing_method: Optional[str] = None

        self.resume_btn = ButtonMorph(
            "Resume",
            x=x + 4,
            y=y + 30,
            width=80,
            height=24,
            on_click=self.on_resume_clicked,
            color="#2d4f3e",
        )
        self.step_btn = ButtonMorph(
            "Step Cycle",
            x=x + 88,
            y=y + 30,
            width=92,
            height=24,
            on_click=self.on_step_clicked,
        )
        self.inspect_self_btn = ButtonMorph(
            "Inspect Self",
            x=x + 184,
            y=y + 30,
            width=104,
            height=24,
            on_click=self.on_inspect_self_clicked,
        )
        self.accept_btn = ButtonMorph(
            "Accept Fix (Cmd+S)",
            x=x + 292,
            y=y + 30,
            width=140,
            height=24,
            on_click=self.on_accept_clicked,
            color="#2d4f3e",
        )

        self.frame_list = ListMorph(
            x=x + 4,
            y=y + 58,
            width=width * 0.48,
            height=130,
            on_select=self.on_frame_selected,
        )
        self.locals_list = ListMorph(
            x=x + 4 + width * 0.48 + 4,
            y=y + 58,
            width=width * 0.48,
            height=130,
        )
        self.code_editor = CodeEditorMorph(
            x=x + 4,
            y=y + 192,
            width=width - 8,
            height=height - 196,
            text="# No exception captured.",
            on_accept=self.on_accept_source,
        )

        self.add_morph(self.resume_btn)
        self.add_morph(self.step_btn)
        self.add_morph(self.inspect_self_btn)
        self.add_morph(self.accept_btn)
        self.add_morph(self.frame_list)
        self.add_morph(self.locals_list)
        self.add_morph(self.code_editor)

        self.load_exception(exc_record)
        self.layout_submorphs()

    def _world(self) -> Any:
        return self.world() or getattr(self, "_world_ref", None)

    def load_exception(self, exc_record: Optional[Dict[str, Any]]) -> None:
        self.exc_record = exc_record
        self.exc_id = exc_record.get("id") if exc_record else None
        if not exc_record:
            self.frame_list.set_items(["<no captured exceptions>"])
            self.locals_list.set_items([])
            self.code_editor.set_text("# No exceptions captured yet.")
            return

        frames: List[Dict[str, Any]] = exc_record.get("frames", [])
        frame_labels = []
        for f in frames:
            cls_prefix = f"{f['self_class']}>>" if f.get("self_class") else ""
            frame_labels.append(f"[{f['index']}] {cls_prefix}{f['function']}:{f['lineno']}")
        if not frame_labels:
            frame_labels = ["<no frames>"]
        self.frame_list.set_items(frame_labels)
        # Default to innermost frame
        innermost = max(0, len(frames) - 1)
        self.frame_list.select_index(innermost, notify=True)

    def on_frame_selected(self, idx: int, _label: str) -> None:
        self.selected_frame_idx = idx
        if not self.exc_record:
            return
        frames = self.exc_record.get("frames", [])
        if not (0 <= idx < len(frames)):
            self.locals_list.set_items([])
            return

        frame = frames[idx]
        locals_items = [f"{k} = {v}" for k, v in frame.get("locals", {}).items()]
        self.locals_list.set_items(locals_items or ["<no locals>"])

        self._editing_class = None
        self._editing_method = None
        w = self._world()
        st = getattr(w, "smalltalk", None) if w else None
        cls_name = frame.get("self_class")
        func_name = frame.get("function")

        if st and cls_name and func_name and st.get_class_record(cls_name):
            src = st.get_method_source(cls_name, func_name)
            if src:
                self._editing_class = cls_name
                self._editing_method = func_name
                self.code_editor.context = {"self": frame.get("_self_obj"), "Smalltalk": st, "World": w}
                self.code_editor.set_text(src)
                return

        self.code_editor.set_text(self.exc_record.get("traceback_text", "# No traceback available"))

    def on_resume_clicked(self) -> None:
        w = self.world()
        if w is not None:
            w.stepping_paused = False
            w.status_message = "Resumed World stepping"
            w.changed()

    def on_step_clicked(self) -> None:
        w = self.world()
        if w is not None:
            w.step_once()
            w.status_message = "Stepped 1 World cycle"
            w.changed()

    def on_inspect_self_clicked(self) -> None:
        if not self.exc_record:
            return
        frames = self.exc_record.get("frames", [])
        target = None
        if 0 <= self.selected_frame_idx < len(frames):
            target = frames[self.selected_frame_idx].get("_self_obj")
        if target is None:
            target = self.exc_record.get("_target_obj")
        w = self.world()
        if w is not None and target is not None:
            w.open_inspector(target)

    def on_accept_clicked(self) -> Any:
        return self.on_accept_source(self.code_editor.get_text())

    def on_accept_source(self, src: Optional[str] = None) -> Any:
        text = src if src is not None else self.code_editor.get_text()
        w = self._world()
        st = getattr(w, "smalltalk", None) if w else None
        if st and self._editing_class:
            try:
                installed = st.compile_and_install_method(
                    self._editing_class,
                    self._editing_method,
                    text,
                    author="debugger",
                )
                if w is not None:
                    w.status_message = f"Hot-patched {self._editing_class}>>{installed}"
                    w.changed()
                return installed
            except Exception as exc:
                if w is not None:
                    w.status_message = f"Compile error: {exc}"
                    w.changed()
                return None
        return self.code_editor.do_it()

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "frame_list"):
            return

        cx = self.x + 4.0
        cy = self.y + self.TITLEBAR_HEIGHT + 4.0
        cw = max(120.0, self.width - 8.0)
        ch = max(120.0, self.height - self.TITLEBAR_HEIGHT - 8.0)

        bx = cx
        for btn in (self.resume_btn, self.step_btn, self.inspect_self_btn, self.accept_btn):
            btn.set_position(bx, cy)
            bx += btn.width + 4.0

        panes_y = cy + 28.0
        top_h = max(60.0, (ch - 32.0) * 0.42)
        half_w = max(50.0, (cw - 4.0) * 0.5)
        self.frame_list.set_bounds(cx, panes_y, half_w, top_h)
        self.locals_list.set_bounds(cx + half_w + 4.0, panes_y, cw - half_w - 4.0, top_h)

        ed_y = panes_y + top_h + 4.0
        ed_h = max(40.0, cy + ch - ed_y)
        self.code_editor.set_bounds(cx, ed_y, cw, ed_h)
