import ast
from typing import Any, Callable, Dict, List, Optional, Tuple
from .canvas import DisplayCanvas
from .morph import Morph


class LabelMorph(Morph):
    """Simple single-line text label Morph."""

    def __init__(
        self,
        text: str,
        x: float = 0,
        y: float = 0,
        color: str = "#e5e9f0",
        font: str = "12px monospace",
    ):
        super().__init__(x, y, max(20, len(text) * 8), 20, color="", border_width=0)
        self.text = text
        self.text_color = color
        self.font = font

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.draw_text(self.text, self.x, self.y + 14, color=self.text_color, font=self.font)


class ButtonMorph(Morph):
    """Interactive clickable button Morph."""

    def __init__(
        self,
        label: str,
        x: float = 0,
        y: float = 0,
        width: float = 84,
        height: float = 24,
        on_click: Optional[Callable[[], Any]] = None,
        color: str = "#3b4252",
        text_color: str = "#eceff4",
    ):
        super().__init__(x, y, width, height, color=color, border_color="#5e81ac", border_width=1.0)
        self.label = label
        self.on_click = on_click
        self.text_color = text_color
        self.is_pressed = False
        self.corner_radius = 4.0

    def trigger(self) -> Any:
        if callable(self.on_click):
            return self.on_click()
        return None

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            self.is_pressed = True
            self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        was_pressed = self.is_pressed
        self.is_pressed = False
        if was_pressed and self.contains_point(px, py):
            self.trigger()
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        bg = "#4c566a" if self.is_pressed else self.color
        canvas.fill_round_rect(
            self.x,
            self.y,
            self.width,
            self.height,
            self.corner_radius,
            bg,
            self.border_color,
            self.border_width,
        )
        tw = len(self.label) * 7.2
        tx = self.x + max(4.0, (self.width - tw) / 2.0)
        ty = self.y + (self.height / 2.0) + 4.0
        canvas.draw_text(self.label, tx, ty, color=self.text_color, font="12px monospace")


class ListMorph(Morph):
    """Scrollable single-selection list Morph used in the 4-pane System Browser and Inspector."""

    ROW_HEIGHT = 20.0
    SCROLLBAR_WIDTH = 10.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 160,
        height: float = 160,
        items: Optional[List[str]] = None,
        on_select: Optional[Callable[[int, str], None]] = None,
    ):
        super().__init__(x, y, width, height, color="#1e222a", border_color="#434c5e", border_width=1.0)
        self.items: List[str] = list(items) if items else []
        self.selected_index: int = -1
        self.scroll_offset: int = 0
        self.on_select = on_select
        self.clip_submorphs = True
        self.corner_radius = 2.0
        self._dragging_scrollbar: bool = False
        self._scrollbar_drag_offset: float = 0.0

    def _visible_rows(self) -> int:
        return max(1, int(self.height // self.ROW_HEIGHT))

    def _max_scroll(self) -> int:
        return max(0, len(self.items) - self._visible_rows())

    def _clamp_scroll(self) -> None:
        self.scroll_offset = max(0, min(self._max_scroll(), self.scroll_offset))

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self._clamp_scroll()

    def ensure_selection_visible(self) -> None:
        if 0 <= self.selected_index < len(self.items):
            vis = self._visible_rows()
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
            elif self.selected_index >= self.scroll_offset + vis:
                self.scroll_offset = self.selected_index - vis + 1
            self._clamp_scroll()

    def set_items(self, items: List[str], keep_selection: bool = False) -> None:
        old_val = self.selected_item
        self.items = list(items)
        if keep_selection and old_val in self.items:
            self.selected_index = self.items.index(old_val)
        elif self.selected_index >= len(self.items):
            self.selected_index = len(self.items) - 1
        self._clamp_scroll()
        self.changed()

    @property
    def selected_item(self) -> Optional[str]:
        if 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def select_index(self, idx: int, notify: bool = True) -> None:
        if 0 <= idx < len(self.items):
            self.selected_index = idx
            self.ensure_selection_visible()
            if notify and callable(self.on_select):
                self.on_select(idx, self.items[idx])
        else:
            self.selected_index = -1
        self.changed()

    def select_value(self, value: str, notify: bool = False) -> None:
        if value in self.items:
            self.select_index(self.items.index(value), notify=notify)

    def _scrollbar_geometry(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        total = len(self.items)
        vis = self._visible_rows()
        if total <= vis:
            return None
        track_x = self.x + self.width - self.SCROLLBAR_WIDTH - 1.0
        track_y = self.y + 1.0
        track_w = self.SCROLLBAR_WIDTH
        track_h = max(16.0, self.height - 2.0)
        thumb_h = max(18.0, min(track_h, track_h * (vis / float(total))))
        max_sc = max(1, total - vis)
        ratio = max(0.0, min(1.0, self.scroll_offset / float(max_sc)))
        thumb_y = track_y + ratio * (track_h - thumb_h)
        return (track_x, track_y, track_w, track_h, thumb_y, thumb_h)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        sb = self._scrollbar_geometry()
        if sb is not None and px >= sb[0]:
            _tx, ty, _tw, th, thumb_y, thumb_h = sb
            if thumb_y <= py <= thumb_y + thumb_h:
                self._dragging_scrollbar = True
                self._scrollbar_drag_offset = py - thumb_y
            elif py < thumb_y:
                self.scroll_offset = max(0, self.scroll_offset - self._visible_rows())
            else:
                self.scroll_offset = min(self._max_scroll(), self.scroll_offset + self._visible_rows())
            self.changed()
            return

        rel_y = py - self.y
        clicked_row = int(rel_y // self.ROW_HEIGHT) + self.scroll_offset
        if 0 <= clicked_row < len(self.items):
            self.select_index(clicked_row, notify=True)

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if getattr(self, "_dragging_scrollbar", False):
            sb = self._scrollbar_geometry()
            if sb is not None:
                _tx, ty, _tw, th, _thumb_y, thumb_h = sb
                travel = max(1.0, th - thumb_h)
                ratio = max(0.0, min(1.0, (py - getattr(self, "_scrollbar_drag_offset", 0.0) - ty) / travel))
                self.scroll_offset = int(round(ratio * self._max_scroll()))
                self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._dragging_scrollbar = False

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if delta_y == 0:
            return
        rows_step = max(1, min(5, int(round(abs(delta_y) / 25.0))))
        step = rows_step if delta_y > 0 else -rows_step
        self.scroll_offset = max(0, min(self._max_scroll(), self.scroll_offset + step))
        self.changed()

    def on_key_down(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> None:
        if not self.items:
            return
        if key == "ArrowUp":
            new_idx = max(0, (self.selected_index if self.selected_index >= 0 else 0) - 1)
            self.select_index(new_idx, notify=True)
        elif key == "ArrowDown":
            new_idx = min(len(self.items) - 1, (self.selected_index if self.selected_index >= 0 else -1) + 1)
            self.select_index(new_idx, notify=True)
        elif key == "PageUp":
            new_idx = max(0, (self.selected_index if self.selected_index >= 0 else 0) - self._visible_rows())
            self.select_index(new_idx, notify=True)
        elif key == "PageDown":
            new_idx = min(len(self.items) - 1, (self.selected_index if self.selected_index >= 0 else 0) + self._visible_rows())
            self.select_index(new_idx, notify=True)
        elif key == "Home":
            self.select_index(0, notify=True)
        elif key == "End":
            self.select_index(len(self.items) - 1, notify=True)

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        canvas.push_clip(self.x + 1, self.y + 1, self.width - 2, self.height - 2)
        try:
            sb = self._scrollbar_geometry()
            avail_w = self.width - (self.SCROLLBAR_WIDTH if sb is not None else 0.0)
            max_rows = int(self.height // self.ROW_HEIGHT) + 1
            max_chars = max(4, int((avail_w - 14) // 7.4))
            for i in range(max_rows):
                item_idx = self.scroll_offset + i
                if item_idx >= len(self.items):
                    break
                ry = self.y + i * self.ROW_HEIGHT
                is_sel = item_idx == self.selected_index
                if is_sel:
                    canvas.fill_rect(self.x + 1, ry, avail_w - 2, self.ROW_HEIGHT, "#5e81ac")
                label = str(self.items[item_idx])
                if len(label) > max_chars:
                    label = label[: max_chars - 1] + "…"
                fg = "#ffffff" if is_sel else "#d8dee9"
                canvas.draw_text(label, self.x + 6, ry + 14, color=fg, font="12px monospace")

            if sb is not None:
                tx, ty, tw, th, thumb_y, thumb_h = sb
                canvas.fill_rect(tx, ty, tw, th, "#14171d")
                thumb_col = "#88c0d0" if getattr(self, "_dragging_scrollbar", False) else "#4c566a"
                canvas.fill_round_rect(tx + 2, thumb_y, tw - 4, thumb_h, 3.0, thumb_col, "", 0.0)
        finally:
            canvas.pop_clip()


class CodeEditorMorph(Morph):
    """
    Live Smalltalk-style Python Code & Text Editor Morph.
    Supports cursor navigation, selection, scrolling, and commands:
    - Do it (Cmd/Ctrl+D): executes selection or current line
    - Print it (Cmd/Ctrl+P): evaluates and inserts repr(result) inline as selection
    - Inspect it (Cmd/Ctrl+I): evaluates and opens an InspectorWindow on the result
    - Accept (Cmd/Ctrl+S): compiles & saves method/class in System Browser
    """

    LINE_HEIGHT = 18.0
    GUTTER_WIDTH = 34.0
    CHAR_WIDTH = 7.8
    SCROLLBAR_WIDTH = 12.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 400,
        height: float = 200,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        on_accept: Optional[Callable[[str], Any]] = None,
        on_inspect: Optional[Callable[[Any], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="#191d24", border_color="#434c5e", border_width=1.0)
        self.text: str = text
        self.cursor_idx: int = len(text)
        self.selection_start: Optional[int] = None
        self.selection_end: Optional[int] = None
        self.scroll_line: int = 0
        self.scroll_col: int = 0
        self.context: Dict[str, Any] = context if context is not None else {}
        self.on_accept = on_accept
        self.on_inspect = on_inspect
        self.last_output: str = ""
        self.is_dirty: bool = False
        self.corner_radius = 2.0
        self._dragging_scrollbar: bool = False
        self._scrollbar_drag_offset: float = 0.0

    def _visible_lines(self) -> int:
        return max(1, int((self.height - 8.0) // self.LINE_HEIGHT))

    def _visible_cols(self) -> int:
        return max(
            4,
            int((self.width - self.GUTTER_WIDTH - self.SCROLLBAR_WIDTH - 12.0) // self.CHAR_WIDTH),
        )

    def _max_scroll_line(self) -> int:
        total_lines = len(self.text.split("\n"))
        return max(0, total_lines - self._visible_lines())

    def _clamp_scroll(self) -> None:
        self.scroll_line = max(0, min(self._max_scroll_line(), self.scroll_line))
        self.scroll_col = max(0, getattr(self, "scroll_col", 0))

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self._clamp_scroll()

    def ensure_cursor_visible(self) -> None:
        row, col = self._index_to_row_col(self.cursor_idx)
        vis_lines = self._visible_lines()
        if row < self.scroll_line:
            self.scroll_line = row
        elif row >= self.scroll_line + vis_lines:
            self.scroll_line = row - vis_lines + 1

        scroll_col = getattr(self, "scroll_col", 0)
        vis_cols = self._visible_cols()
        if col < scroll_col:
            self.scroll_col = max(0, col - 2)
        elif col >= scroll_col + vis_cols:
            self.scroll_col = col - vis_cols + 2

        self._clamp_scroll()

    def set_text(self, new_text: str) -> None:
        self.text = str(new_text)
        self.cursor_idx = 0
        self.selection_start = None
        self.selection_end = None
        self.scroll_line = 0
        self.scroll_col = 0
        self.is_dirty = False
        self.changed()

    def select_all(self) -> None:
        self.selection_start = 0
        self.selection_end = len(self.text)
        self.cursor_idx = len(self.text)
        self.changed()

    def has_selection(self) -> bool:
        return (
            self.selection_start is not None
            and self.selection_end is not None
            and self.selection_start != self.selection_end
        )

    def get_selection_range(self) -> Tuple[int, int]:
        if not self.has_selection():
            return (self.cursor_idx, self.cursor_idx)
        lo = min(int(self.selection_start), int(self.selection_end))
        hi = max(int(self.selection_start), int(self.selection_end))
        return (max(0, lo), min(len(self.text), hi))

    def get_selected_or_active_text(self) -> str:
        if self.has_selection():
            lo, hi = self.get_selection_range()
            return self.text[lo:hi]
        # Otherwise, if cursor is on a non-empty line, return that line; or full text
        lines = self.text.splitlines()
        if not lines:
            return ""
        row, _col = self._index_to_row_col(self.cursor_idx)
        if 0 <= row < len(lines) and lines[row].strip():
            return lines[row]
        return self.text

    def evaluate_code(self, code_str: str) -> Any:
        """
        Executes a Python snippet in `self.context` (merged with World/Smalltalk globals)
        and returns the value of the final expression (if any), just like Smalltalk Do-It!
        """
        code_str = code_str.strip()
        if not code_str:
            return None

        w = self.world()
        env: Dict[str, Any] = {}
        if w is not None:
            env.update(w.workspace_globals)
            if w.smalltalk is not None:
                env.update(w.smalltalk.global_namespace)
        if self.context is not None:
            env.update(self.context)

        tree = ast.parse(code_str, filename="<ObjectPond-DoIt>", mode="exec")
        if not tree.body:
            return None

        last_node = tree.body[-1]
        if isinstance(last_node, ast.Expr):
            if len(tree.body) > 1:
                prefix_mod = ast.Module(body=tree.body[:-1], type_ignores=[])
                exec(compile(prefix_mod, "<ObjectPond-DoIt>", "exec"), env)
            expr_ast = ast.Expression(body=last_node.value)
            result = eval(compile(expr_ast, "<ObjectPond-DoIt>", "eval"), env)
        else:
            exec(compile(tree, "<ObjectPond-DoIt>", "exec"), env)
            result = None

        # Persist newly assigned user variables back into self.context / workspace_globals
        if self.context is not None:
            for k, v in env.items():
                if not k.startswith("__"):
                    self.context[k] = v
        if w is not None:
            w.changed()
        return result

    def do_it(self) -> Any:
        snippet = self.get_selected_or_active_text()
        try:
            res = self.evaluate_code(snippet)
            self.last_output = repr(res)
            w = self.world()
            if w is not None:
                w.status_message = f"Do it -> {repr(res)[:60]}"
            return res
        except Exception as exc:
            self.last_output = f"Error: {exc}"
            w = self.world()
            if w is not None:
                w.status_message = f"Error: {exc}"
                if w.smalltalk:
                    w.smalltalk.log_transcript(f"Evaluation Error: {exc}")
            return exc

    def print_it(self) -> str:
        res = self.do_it()
        printed = repr(res)
        if self.has_selection():
            _lo, hi = self.get_selection_range()
            insert_at = hi
        else:
            insert_at = self.cursor_idx
        insertion = f" {printed}"
        self.text = self.text[:insert_at] + insertion + self.text[insert_at:]
        self.selection_start = insert_at + 1
        self.selection_end = insert_at + len(insertion)
        self.cursor_idx = self.selection_end
        self.changed()
        return printed

    def inspect_it(self) -> Any:
        res = self.do_it()
        if callable(self.on_inspect):
            self.on_inspect(res)
        else:
            w = self.world()
            if w is not None:
                w.open_inspector(res)
        return res

    def accept(self) -> Any:
        if callable(self.on_accept):
            res = self.on_accept(self.text)
            self.is_dirty = False
            self.changed()
            return res
        return self.do_it()

    # --- Text Editing & Cursor Helpers ---
    def _index_to_row_col(self, idx: int) -> Tuple[int, int]:
        idx = max(0, min(len(self.text), idx))
        prefix = self.text[:idx]
        lines = prefix.split("\n")
        return (len(lines) - 1, len(lines[-1]))

    def _row_col_to_index(self, row: int, col: int) -> int:
        lines = self.text.split("\n")
        if not lines:
            return 0
        row = max(0, min(len(lines) - 1, row))
        col = max(0, min(len(lines[row]), col))
        return sum(len(lines[r]) + 1 for r in range(row)) + col

    def _point_to_index(self, px: float, py: float) -> int:
        rel_y = py - (self.y + 4.0)
        rel_x = max(0.0, px - (self.x + self.GUTTER_WIDTH + 6.0))
        row = int(rel_y // self.LINE_HEIGHT) + self.scroll_line
        col = int(round(rel_x / self.CHAR_WIDTH)) + getattr(self, "scroll_col", 0)
        return self._row_col_to_index(row, col)

    def _scrollbar_geometry(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        total = len(self.text.split("\n"))
        vis = self._visible_lines()
        if total <= vis:
            return None
        track_x = self.x + self.width - self.SCROLLBAR_WIDTH - 1.0
        track_y = self.y + 1.0
        track_w = self.SCROLLBAR_WIDTH
        # Leave space at bottom-right if flush with enclosing window's resize grip
        bottom_pad = 2.0
        if (
            self.owner is not None
            and hasattr(self.owner, "RESIZE_GRIP_SIZE")
            and abs((self.y + self.height) - (self.owner.y + self.owner.height)) <= 8.0
        ):
            bottom_pad = 14.0
        track_h = max(20.0, self.height - bottom_pad)
        thumb_h = max(20.0, min(track_h, track_h * (vis / float(total))))
        max_sc = max(1, total - vis)
        ratio = max(0.0, min(1.0, self.scroll_line / float(max_sc)))
        thumb_y = track_y + ratio * (track_h - thumb_h)
        return (track_x, track_y, track_w, track_h, thumb_y, thumb_h)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            sb = self._scrollbar_geometry()
            if sb is not None and px >= sb[0]:
                _tx, ty, _tw, th, thumb_y, thumb_h = sb
                if thumb_y <= py <= thumb_y + thumb_h:
                    self._dragging_scrollbar = True
                    self._scrollbar_drag_offset = py - thumb_y
                elif py < thumb_y:
                    self.scroll_line = max(0, self.scroll_line - self._visible_lines())
                else:
                    self.scroll_line = min(
                        self._max_scroll_line(), self.scroll_line + self._visible_lines()
                    )
                self.changed()
                return

            idx = self._point_to_index(px, py)
            self.cursor_idx = idx
            self.selection_start = idx
            self.selection_end = idx
            self.ensure_cursor_visible()
            self.changed()

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if getattr(self, "_dragging_scrollbar", False):
            sb = self._scrollbar_geometry()
            if sb is not None:
                _tx, ty, _tw, th, _thumb_y, thumb_h = sb
                travel = max(1.0, th - thumb_h)
                ratio = max(
                    0.0,
                    min(1.0, (py - getattr(self, "_scrollbar_drag_offset", 0.0) - ty) / travel),
                )
                self.scroll_line = int(round(ratio * self._max_scroll_line()))
                self.changed()
            return

        # Auto-scroll when drag-selecting above or below the viewport
        if py < self.y + 4.0:
            self.scroll_line = max(0, self.scroll_line - 1)
        elif py > self.y + self.height - 4.0:
            self.scroll_line = min(self._max_scroll_line(), self.scroll_line + 1)

        idx = self._point_to_index(px, py)
        self.selection_end = idx
        self.cursor_idx = idx
        self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._dragging_scrollbar = False

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if delta_y == 0:
            return
        lines_step = max(1, min(6, int(round(abs(delta_y) / 20.0))))
        step = lines_step if delta_y > 0 else -lines_step
        self.scroll_line = max(0, min(self._max_scroll_line(), self.scroll_line + step))
        self.changed()

    def insert_text(self, s: str) -> None:
        if self.has_selection():
            lo, hi = self.get_selection_range()
            self.text = self.text[:lo] + s + self.text[hi:]
            self.cursor_idx = lo + len(s)
            self.selection_start = None
            self.selection_end = None
        else:
            self.text = self.text[: self.cursor_idx] + s + self.text[self.cursor_idx :]
            self.cursor_idx += len(s)
        self.is_dirty = True
        self.ensure_cursor_visible()
        self.changed()

    def _move_cursor(self, new_idx: int, extend_selection: bool = False) -> None:
        new_idx = max(0, min(len(self.text), new_idx))
        if extend_selection:
            if self.selection_start is None:
                self.selection_start = self.cursor_idx
            self.selection_end = new_idx
        else:
            self.selection_start = None
            self.selection_end = None
        self.cursor_idx = new_idx
        self.ensure_cursor_visible()

    def on_key_down(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> None:
        cmd = ctrl_key or meta_key
        if cmd:
            k_lower = key.lower()
            if k_lower == "d":
                self.do_it()
                return
            if k_lower == "p":
                self.print_it()
                return
            if k_lower == "i":
                self.inspect_it()
                return
            if k_lower == "s":
                self.accept()
                return
            if k_lower == "a":
                self.select_all()
                return
            if key == "ArrowUp":
                self._move_cursor(0, extend_selection=shift_key)
                self.changed()
                return
            if key == "ArrowDown":
                self._move_cursor(len(self.text), extend_selection=shift_key)
                self.changed()
                return
            if key == "ArrowLeft":
                row, _col = self._index_to_row_col(self.cursor_idx)
                self._move_cursor(self._row_col_to_index(row, 0), extend_selection=shift_key)
                self.changed()
                return
            if key == "ArrowRight":
                row, _col = self._index_to_row_col(self.cursor_idx)
                lines = self.text.split("\n")
                line_len = len(lines[row]) if 0 <= row < len(lines) else 0
                self._move_cursor(self._row_col_to_index(row, line_len), extend_selection=shift_key)
                self.changed()
                return

        if key == "Backspace":
            if self.has_selection():
                self.insert_text("")
            elif self.cursor_idx > 0:
                self.text = self.text[: self.cursor_idx - 1] + self.text[self.cursor_idx :]
                self.cursor_idx -= 1
                self.is_dirty = True
                self.ensure_cursor_visible()
        elif key == "Delete":
            if self.has_selection():
                self.insert_text("")
            elif self.cursor_idx < len(self.text):
                self.text = self.text[: self.cursor_idx] + self.text[self.cursor_idx + 1 :]
                self.is_dirty = True
                self.ensure_cursor_visible()
        elif key == "Enter":
            row, _col = self._index_to_row_col(self.cursor_idx)
            lines = self.text.split("\n")
            curr_line = lines[row] if 0 <= row < len(lines) else ""
            indent = len(curr_line) - len(curr_line.lstrip(" "))
            if curr_line.rstrip().endswith(":"):
                indent += 4
            self.insert_text("\n" + (" " * indent))
        elif key == "Tab":
            self.insert_text("    ")
        elif key == "ArrowLeft":
            self._move_cursor(self.cursor_idx - 1, extend_selection=shift_key)
        elif key == "ArrowRight":
            self._move_cursor(self.cursor_idx + 1, extend_selection=shift_key)
        elif key == "ArrowUp":
            row, col = self._index_to_row_col(self.cursor_idx)
            self._move_cursor(self._row_col_to_index(max(0, row - 1), col), extend_selection=shift_key)
        elif key == "ArrowDown":
            row, col = self._index_to_row_col(self.cursor_idx)
            self._move_cursor(self._row_col_to_index(row + 1, col), extend_selection=shift_key)
        elif key == "PageUp":
            row, col = self._index_to_row_col(self.cursor_idx)
            vis = self._visible_lines()
            self.scroll_line = max(0, self.scroll_line - vis)
            self._move_cursor(self._row_col_to_index(max(0, row - vis), col), extend_selection=shift_key)
        elif key == "PageDown":
            row, col = self._index_to_row_col(self.cursor_idx)
            vis = self._visible_lines()
            self.scroll_line = min(self._max_scroll_line(), self.scroll_line + vis)
            self._move_cursor(self._row_col_to_index(row + vis, col), extend_selection=shift_key)
        elif key == "Home":
            row, _col = self._index_to_row_col(self.cursor_idx)
            self._move_cursor(self._row_col_to_index(row, 0), extend_selection=shift_key)
        elif key == "End":
            row, _col = self._index_to_row_col(self.cursor_idx)
            lines = self.text.split("\n")
            line_len = len(lines[row]) if 0 <= row < len(lines) else 0
            self._move_cursor(self._row_col_to_index(row, line_len), extend_selection=shift_key)
        elif len(key) == 1 and not cmd:
            self.insert_text(key)
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.fill_rect(self.x, self.y, self.GUTTER_WIDTH, self.height, "#14171d")
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)

        canvas.push_clip(self.x + 1, self.y + 1, self.width - 2, self.height - 2)
        try:
            lines = self.text.split("\n")
            max_visible = int(self.height // self.LINE_HEIGHT) + 1
            sel_lo, sel_hi = self.get_selection_range()
            cursor_row, cursor_col = self._index_to_row_col(self.cursor_idx)
            scroll_col = getattr(self, "scroll_col", 0)
            sb = self._scrollbar_geometry()
            text_clip_w = max(
                10.0,
                self.width
                - self.GUTTER_WIDTH
                - (self.SCROLLBAR_WIDTH if sb is not None else 0.0)
                - 2.0,
            )

            w = self.world()
            has_focus = w is not None and w.hand.keyboard_focus is self

            for vis_i in range(max_visible):
                line_idx = self.scroll_line + vis_i
                if line_idx >= len(lines):
                    break
                ly = self.y + 4.0 + vis_i * self.LINE_HEIGHT
                line_str = lines[line_idx]

                # Draw line number in gutter
                canvas.draw_text(
                    f"{line_idx + 1:>3}",
                    self.x + 4,
                    ly + 13,
                    color="#4c566a",
                    font="11px monospace",
                )

            # Clip code text & caret to text region between gutter and scrollbar
            canvas.push_clip(self.x + self.GUTTER_WIDTH, self.y + 1, text_clip_w, self.height - 2)
            try:
                for vis_i in range(max_visible):
                    line_idx = self.scroll_line + vis_i
                    if line_idx >= len(lines):
                        break
                    ly = self.y + 4.0 + vis_i * self.LINE_HEIGHT
                    line_str = lines[line_idx]

                    # Draw selection highlight if line intersects selection
                    if self.has_selection():
                        line_start = self._row_col_to_index(line_idx, 0)
                        line_end = line_start + len(line_str)
                        over_lo = max(sel_lo, line_start)
                        over_hi = min(sel_hi, line_end)
                        if over_hi > over_lo:
                            sx = (
                                self.x
                                + self.GUTTER_WIDTH
                                + 6
                                + (over_lo - line_start - scroll_col) * self.CHAR_WIDTH
                            )
                            sw = max(6.0, (over_hi - over_lo) * self.CHAR_WIDTH)
                            canvas.fill_rect(sx, ly, sw, self.LINE_HEIGHT, "#3b536e")

                    # Simple syntax coloring for Python keywords/comments
                    fg = "#eceff4"
                    stripped = line_str.lstrip()
                    if stripped.startswith("#"):
                        fg = "#7c8698"
                    elif stripped.startswith(("def ", "class ", "return ", "import ", "from ")):
                        fg = "#88c0d0"
                    visible_str = line_str[scroll_col:] if scroll_col < len(line_str) else ""
                    canvas.draw_text(
                        visible_str,
                        self.x + self.GUTTER_WIDTH + 6,
                        ly + 13,
                        color=fg,
                        font="13px monospace",
                    )

                    # Draw cursor caret
                    if line_idx == cursor_row and cursor_col >= scroll_col:
                        cx = (
                            self.x
                            + self.GUTTER_WIDTH
                            + 6
                            + (cursor_col - scroll_col) * self.CHAR_WIDTH
                        )
                        caret_color = "#ebcb8b" if has_focus else "#616e88"
                        canvas.fill_rect(cx, ly + 1, 2.0, self.LINE_HEIGHT - 2, caret_color)
            finally:
                canvas.pop_clip()

            # Draw vertical scrollbar if document exceeds visible lines
            if sb is not None:
                tx, ty, tw, th, thumb_y, thumb_h = sb
                canvas.fill_rect(tx, ty, tw, th, "#14171d")
                thumb_col = (
                    "#88c0d0" if getattr(self, "_dragging_scrollbar", False) else "#4c566a"
                )
                canvas.fill_round_rect(
                    tx + 2, thumb_y, tw - 4, thumb_h, 3.0, thumb_col, "", 0.0
                )

            # Unsaved dirty indicator triangle in top-right corner (classic Smalltalk orange corner!)
            if self.is_dirty:
                dirty_x = (
                    self.x + self.width - self.SCROLLBAR_WIDTH - 10
                    if sb is not None
                    else self.x + self.width - 10
                )
                canvas.fill_rect(dirty_x, self.y + 2, 8, 8, "#ebcb8b")
        finally:
            canvas.pop_clip()


class MenuMorph(Morph):
    """Popup menu Morph for World menu and context actions."""

    ITEM_HEIGHT = 24.0

    def __init__(
        self,
        x: float,
        y: float,
        items: List[Tuple[str, Callable[[], Any]]],
    ):
        max_len = max((len(label) for label, _ in items), default=16)
        w = max(180.0, max_len * 7.8 + 24)
        h = len(items) * self.ITEM_HEIGHT + 8
        super().__init__(x, y, w, h, color="#1e222a", border_color="#88c0d0", border_width=1.5)
        self.items = items
        self.corner_radius = 6.0

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        idx = int((py - (self.y + 4)) // self.ITEM_HEIGHT)
        if 0 <= idx < len(self.items):
            _label, callback = self.items[idx]
            if callable(callback):
                callback()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x,
            self.y,
            self.width,
            self.height,
            self.corner_radius,
            self.color,
            self.border_color,
            self.border_width,
        )
        for idx, (label, _cb) in enumerate(self.items):
            iy = self.y + 4 + idx * self.ITEM_HEIGHT
            canvas.draw_text(label, self.x + 12, iy + 16, color="#eceff4", font="12px monospace")
            if idx < len(self.items) - 1:
                canvas.draw_line(
                    self.x + 6,
                    iy + self.ITEM_HEIGHT,
                    self.x + self.width - 6,
                    iy + self.ITEM_HEIGHT,
                    "#2e3440",
                    1.0,
                )


class SystemWindowMorph(Morph):
    """
    Classic SystemWindow with color-coded title bar, close box, collapse toggle,
    and bottom-right resize handle.
    """

    TITLEBAR_HEIGHT = 26.0
    RESIZE_GRIP_SIZE = 16.0

    def __init__(
        self,
        title: str = "System Window",
        x: float = 60,
        y: float = 60,
        width: float = 480,
        height: float = 340,
        header_color: str = "#3b536e",
    ):
        super().__init__(
            x,
            y,
            width,
            height,
            color="#252b37",
            border_color="#4c566a",
            border_width=1.5,
        )
        self.title = title
        self.header_color = header_color
        self.is_collapsed = False
        self.expanded_height = float(height)
        self.corner_radius = 6.0

    def toggle_collapse(self) -> None:
        if not self.is_collapsed:
            self.expanded_height = self.height
            self.is_collapsed = True
            self.height = self.TITLEBAR_HEIGHT
            for sub in self.submorphs:
                sub.visible = False
        else:
            self.is_collapsed = False
            self.height = self.expanded_height
            for sub in self.submorphs:
                sub.visible = True
        self.changed()

    def _in_close_box(self, px: float, py: float) -> bool:
        return (
            self.x + 8 <= px <= self.x + 24
            and self.y + 4 <= py <= self.y + 22
        )

    def _in_collapse_box(self, px: float, py: float) -> bool:
        return (
            self.x + self.width - 26 <= px <= self.x + self.width - 8
            and self.y + 4 <= py <= self.y + 22
        )

    def _in_resize_grip(self, px: float, py: float) -> bool:
        if self.is_collapsed:
            return False
        return (
            px >= self.x + self.width - self.RESIZE_GRIP_SIZE
            and py >= self.y + self.height - self.RESIZE_GRIP_SIZE
        )

    def morph_at(self, px: float, py: float) -> Optional["Morph"]:
        if not self.visible:
            return None
        if self.contains_point(px, py) and (
            self._in_resize_grip(px, py)
            or self._in_close_box(px, py)
            or self._in_collapse_box(px, py)
        ):
            return self
        return super().morph_at(px, py)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        self.bring_to_front()
        w = self.world()
        if self._in_close_box(px, py):
            self.delete()
            return
        if self._in_collapse_box(px, py):
            self.toggle_collapse()
            return
        if self._in_resize_grip(px, py) and w is not None:
            w.hand.drag_target = self
            w.hand.drag_mode = "resize"
            return
        if py <= self.y + self.TITLEBAR_HEIGHT and w is not None:
            w.hand.drag_target = self
            w.hand.drag_mode = "move"

    def draw_on(self, canvas: DisplayCanvas) -> None:
        # Window body
        canvas.fill_round_rect(
            self.x,
            self.y,
            self.width,
            self.height,
            self.corner_radius,
            self.color,
            self.border_color,
            self.border_width,
        )
        # Header bar
        canvas.fill_round_rect(
            self.x,
            self.y,
            self.width,
            self.TITLEBAR_HEIGHT,
            self.corner_radius,
            self.header_color,
            self.border_color,
            1.0,
        )
        # Close button (red circle)
        canvas.fill_circle(self.x + 15, self.y + 13, 6.5, "#bf616a", "#1e222a", 1.0)
        # Collapse button (yellow circle)
        canvas.fill_circle(self.x + self.width - 16, self.y + 13, 6.5, "#ebcb8b", "#1e222a", 1.0)

        # Window Title
        canvas.draw_text(
            self.title,
            self.x + 30,
            self.y + 17,
            color="#eceff4",
            font="bold 12px monospace",
        )

    def full_draw_on(self, canvas: DisplayCanvas) -> None:
        super().full_draw_on(canvas)
        # Draw bottom-right resize grip on top of child submorphs so it is always visible
        if self.visible and not self.is_collapsed:
            gx = self.x + self.width - 14
            gy = self.y + self.height - 14
            canvas.draw_line(gx + 3, gy + 12, gx + 12, gy + 3, "#88c0d0", 1.5)
            canvas.draw_line(gx + 7, gy + 12, gx + 12, gy + 7, "#88c0d0", 1.5)
