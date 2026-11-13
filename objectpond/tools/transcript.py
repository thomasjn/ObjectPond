from typing import Any, Optional
from objectpond.morphic.widgets import (
    SystemWindowMorph,
    ButtonMorph,
    ListMorph,
    CodeEditorMorph,
)


class TranscriptWindow(SystemWindowMorph):
    """
    Classic Smalltalk Transcript window.
    Displays messages logged via `Transcript.show(...)` or `Smalltalk.log_transcript(...)`.
    """

    def __init__(
        self,
        world: Any,
        x: float = 700,
        y: float = 405,
        width: float = 540,
        height: float = 220,
    ):
        super().__init__(
            title="Transcript",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b536e",
        )
        self._smalltalk = getattr(world, "smalltalk", None)
        self._last_history_len: int = 0

        self.clear_btn = ButtonMorph(
            "Clear",
            x=x + 4,
            y=y + 30,
            width=70,
            height=24,
            on_click=self.on_clear_clicked,
        )

        initial_history = self.smalltalk.transcript_history if self.smalltalk else []
        self._last_history_len = len(initial_history)
        self.editor = CodeEditorMorph(
            x=x + 4,
            y=y + 58,
            width=width - 8,
            height=height - 64,
            text="\n".join(initial_history),
        )

        self.add_morph(self.clear_btn)
        self.add_morph(self.editor)
        self.layout_submorphs()

    @property
    def smalltalk(self) -> Optional[Any]:
        if self._smalltalk is not None:
            return self._smalltalk
        w = self.world()
        if w is not None and getattr(w, "smalltalk", None) is not None:
            return w.smalltalk
        return None

    @smalltalk.setter
    def smalltalk(self, val: Any) -> None:
        self._smalltalk = val

    def on_clear_clicked(self) -> None:
        if self.smalltalk is not None:
            self.smalltalk.transcript_history.clear()
        self._last_history_len = 0
        self.editor.set_text("")

    def wants_steps(self) -> bool:
        return True

    def step(self) -> None:
        st = self.smalltalk
        if st is not None:
            cur_len = len(st.transcript_history)
            if cur_len != self._last_history_len:
                self._last_history_len = cur_len
                self.editor.set_text("\n".join(st.transcript_history))
                self.editor.cursor_idx = len(self.editor.text)
                self.editor.ensure_cursor_visible()

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "clear_btn"):
            return

        bx = self.x + 4.0
        by = self.y + self.TITLEBAR_HEIGHT + 4.0
        self.clear_btn.set_position(bx, by)

        ey = by + 28.0
        ew = max(100.0, self.width - 8.0)
        eh = max(40.0, self.y + self.height - ey - 4.0)
        self.editor.set_bounds(self.x + 4.0, ey, ew, eh)


class ChangesViewerWindow(SystemWindowMorph):
    """
    Classic Smalltalk Changes Log viewer.
    Displays every audit log entry from `ChangesLog` (.changes file format)
    allowing users to review class/method modifications and inspect the historical source.
    """

    def __init__(
        self,
        world: Any,
        x: float = 460,
        y: float = 160,
        width: float = 580,
        height: float = 380,
    ):
        super().__init__(
            title="Changes Log Viewer",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b536e",
        )
        self._smalltalk = getattr(world, "smalltalk", None)
        self._last_entries_len: int = -1

        self.refresh_btn = ButtonMorph(
            "Refresh",
            x=x + 4,
            y=y + 30,
            width=80,
            height=24,
            on_click=self.on_refresh_clicked,
        )

        self.entry_list = ListMorph(
            x=x + 4,
            y=y + 58,
            width=220,
            height=height - 64,
            on_select=self.on_entry_selected,
        )

        self.source_editor = CodeEditorMorph(
            x=x + 228,
            y=y + 58,
            width=width - 232,
            height=height - 64,
            text="",
        )

        self.add_morph(self.refresh_btn)
        self.add_morph(self.entry_list)
        self.add_morph(self.source_editor)

        self.refresh_entries()
        self.layout_submorphs()
        if self.entry_list.items:
            self.entry_list.select_index(len(self.entry_list.items) - 1, notify=True)

    @property
    def smalltalk(self) -> Optional[Any]:
        if self._smalltalk is not None:
            return self._smalltalk
        w = self.world()
        if w is not None and getattr(w, "smalltalk", None) is not None:
            return w.smalltalk
        return None

    @smalltalk.setter
    def smalltalk(self, val: Any) -> None:
        self._smalltalk = val

    def on_refresh_clicked(self) -> None:
        self.refresh_entries()

    def refresh_entries(self) -> None:
        st = self.smalltalk
        entries = st.changes_log.entries if st and hasattr(st, "changes_log") else []
        self._last_entries_len = len(entries)
        items = []
        for e in entries:
            kind = e.get("kind", "Change")
            target = e.get("target", "")
            items.append(f"{kind}: {target}")
        self.entry_list.set_items(items, keep_selection=True)

    def on_entry_selected(self, idx: int, item: str) -> None:
        st = self.smalltalk
        entries = st.changes_log.entries if st and hasattr(st, "changes_log") else []
        if 0 <= idx < len(entries):
            e = entries[idx]
            header = (
                f"# Kind: {e.get('kind')} | Target: {e.get('target')}\n"
                f"# Author: {e.get('author')} | Timestamp: {e.get('timestamp')}\n"
                f"# Protocol: {e.get('protocol')}\n\n"
            )
            self.source_editor.set_text(header + e.get("source", ""))

    def wants_steps(self) -> bool:
        return True

    def step(self) -> None:
        st = self.smalltalk
        if st and hasattr(st, "changes_log"):
            cur_len = len(st.changes_log.entries)
            if cur_len != self._last_entries_len:
                self.refresh_entries()

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "entry_list"):
            return

        bx = self.x + 4.0
        by = self.y + self.TITLEBAR_HEIGHT + 4.0
        self.refresh_btn.set_position(bx, by)

        content_y = by + 28.0
        content_w = max(100.0, self.width - 8.0)
        content_h = max(40.0, self.y + self.height - content_y - 4.0)

        list_w = max(100.0, min(240.0, content_w * 0.40))
        self.entry_list.set_bounds(bx, content_y, list_w, content_h)

        sx = bx + list_w + 4.0
        sw = max(60.0, content_w - list_w - 4.0)
        self.source_editor.set_bounds(sx, content_y, sw, content_h)
