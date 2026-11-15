from typing import Any, Callable, Dict, List, Optional, Tuple
from objectpond.morphic.canvas import DisplayCanvas, Form
from objectpond.morphic.morph import Morph
from objectpond.morphic.widgets import ButtonMorph, MenuMorph


class TextInputMorph(Morph):
    """Single-line text input field with placeholder, masking, selection, and clipboard support."""

    CHAR_WIDTH = 7.8
    SCROLL_PAD = 8.0
    _clipboard_fallback: str = ""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 200,
        height: float = 28,
        text: str = "",
        placeholder: str = "",
        password: bool = False,
        on_change: Optional[Callable[[str], Any]] = None,
        on_submit: Optional[Callable[[str], Any]] = None,
    ):
        super().__init__(
            x,
            y,
            width,
            height,
            color="#1b1f27",
            border_color="#4c566a",
            border_width=1.0,
        )
        self.corner_radius = 4.0
        self.text: str = str(text)
        self.placeholder: str = str(placeholder)
        self.password: bool = password
        self.on_change = on_change
        self.on_submit = on_submit
        self.cursor_idx: int = len(self.text)
        self.selection_start: Optional[int] = None
        self.selection_end: Optional[int] = None
        self.scroll_col: int = 0

    def _display_text(self) -> str:
        return ("*" * len(self.text)) if self.password else self.text

    def _visible_cols(self) -> int:
        return max(3, int((self.width - self.SCROLL_PAD * 2) // self.CHAR_WIDTH))

    def _ensure_cursor_visible(self) -> None:
        vis = self._visible_cols()
        if self.cursor_idx < self.scroll_col:
            self.scroll_col = max(0, self.cursor_idx - 2)
        elif self.cursor_idx >= self.scroll_col + vis:
            self.scroll_col = max(0, self.cursor_idx - vis + 2)
        max_sc = max(0, len(self.text) - vis)
        self.scroll_col = max(0, min(max_sc, self.scroll_col))

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

    def select_all(self) -> None:
        self.selection_start = 0
        self.selection_end = len(self.text)
        self.cursor_idx = len(self.text)
        self._ensure_cursor_visible()
        self.changed()

    def set_text(self, value: str, notify: bool = False) -> None:
        self.text = str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        self.cursor_idx = min(self.cursor_idx, len(self.text))
        self.selection_start = None
        self.selection_end = None
        self._ensure_cursor_visible()
        if notify and callable(self.on_change):
            self.on_change(self.text)
        self.changed()

    def _get_clipboard(self) -> str:
        w = self.world()
        if w is not None and hasattr(w, "get_clipboard_text"):
            return w.get_clipboard_text()
        return TextInputMorph._clipboard_fallback

    def _set_clipboard(self, value: str) -> None:
        w = self.world()
        if w is not None and hasattr(w, "set_clipboard_text"):
            w.set_clipboard_text(value)
        else:
            TextInputMorph._clipboard_fallback = str(value)

    def copy_selection(self) -> str:
        if not self.has_selection():
            return ""
        lo, hi = self.get_selection_range()
        selected = self.text[lo:hi]
        self._set_clipboard(selected)
        return selected

    def cut_selection(self) -> str:
        if not self.has_selection():
            return ""
        selected = self.copy_selection()
        self.insert_text("")
        return selected

    def paste_from_clipboard(self, value: Optional[str] = None) -> str:
        clip = self._get_clipboard() if value is None else str(value)
        clean = clip.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        if clean:
            self.insert_text(clean)
        return clean

    def on_paste(self, text: str) -> None:
        self._set_clipboard(str(text))
        self.paste_from_clipboard(text)

    def insert_text(self, s: str) -> None:
        s = str(s).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        if self.has_selection():
            lo, hi = self.get_selection_range()
            self.text = self.text[:lo] + s + self.text[hi:]
            self.cursor_idx = lo + len(s)
            self.selection_start = None
            self.selection_end = None
        else:
            self.text = self.text[: self.cursor_idx] + s + self.text[self.cursor_idx :]
            self.cursor_idx += len(s)
        self._ensure_cursor_visible()
        if callable(self.on_change):
            self.on_change(self.text)
        self.changed()

    def _point_to_index(self, px: float) -> int:
        rel_x = max(0.0, px - (self.x + self.SCROLL_PAD))
        col = int(round(rel_x / self.CHAR_WIDTH)) + self.scroll_col
        return max(0, min(len(self.text), col))

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
        self._ensure_cursor_visible()

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            idx = self._point_to_index(px)
            self.cursor_idx = idx
            self.selection_start = idx
            self.selection_end = idx
            self._ensure_cursor_visible()
            self.changed()

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        idx = self._point_to_index(px)
        self.selection_end = idx
        self.cursor_idx = idx
        self._ensure_cursor_visible()
        self.changed()

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
            kl = key.lower()
            if kl == "a":
                self.select_all()
                return
            if kl == "c":
                self.copy_selection()
                return
            if kl == "x":
                self.cut_selection()
                return
            if kl == "v":
                self.paste_from_clipboard()
                return

        if key == "Enter":
            if callable(self.on_submit):
                self.on_submit(self.text)
            return
        if key == "Backspace":
            if self.has_selection():
                self.insert_text("")
            elif self.cursor_idx > 0:
                self.text = self.text[: self.cursor_idx - 1] + self.text[self.cursor_idx :]
                self.cursor_idx -= 1
                self._ensure_cursor_visible()
                if callable(self.on_change):
                    self.on_change(self.text)
                self.changed()
            return
        if key == "Delete":
            if self.has_selection():
                self.insert_text("")
            elif self.cursor_idx < len(self.text):
                self.text = self.text[: self.cursor_idx] + self.text[self.cursor_idx + 1 :]
                if callable(self.on_change):
                    self.on_change(self.text)
                self.changed()
            return
        if key == "ArrowLeft":
            self._move_cursor(self.cursor_idx - 1, extend_selection=shift_key)
            self.changed()
            return
        if key == "ArrowRight":
            self._move_cursor(self.cursor_idx + 1, extend_selection=shift_key)
            self.changed()
            return
        if key == "Home":
            self._move_cursor(0, extend_selection=shift_key)
            self.changed()
            return
        if key == "End":
            self._move_cursor(len(self.text), extend_selection=shift_key)
            self.changed()
            return
        if len(key) == 1 and not cmd and not alt_key:
            self.insert_text(key)

    def draw_on(self, canvas: DisplayCanvas) -> None:
        w = self.world()
        has_focus = w is not None and w.hand.keyboard_focus is self
        border = "#88c0d0" if has_focus else self.border_color
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius, self.color, border, 1.2 if has_focus else 1.0
        )
        canvas.push_clip(self.x + 2, self.y + 2, max(4.0, self.width - 4), max(4.0, self.height - 4))
        try:
            text_y = self.y + self.height / 2.0 + 4.5
            disp = self._display_text()
            if self.has_selection():
                lo, hi = self.get_selection_range()
                sx = self.x + self.SCROLL_PAD + (lo - self.scroll_col) * self.CHAR_WIDTH
                sw = max(4.0, (hi - lo) * self.CHAR_WIDTH)
                canvas.fill_rect(sx, self.y + 4, sw, max(8.0, self.height - 8), "#3b536e")

            if disp:
                vis_str = disp[self.scroll_col :] if self.scroll_col < len(disp) else ""
                canvas.draw_text(vis_str, self.x + self.SCROLL_PAD, text_y, color="#eceff4", font="13px monospace")
            elif self.placeholder:
                canvas.draw_text(self.placeholder, self.x + self.SCROLL_PAD, text_y, color="#616e88", font="12px sans-serif")

            if has_focus and self.cursor_idx >= self.scroll_col:
                cx = self.x + self.SCROLL_PAD + (self.cursor_idx - self.scroll_col) * self.CHAR_WIDTH
                canvas.fill_rect(cx, self.y + 5, 2.0, max(8.0, self.height - 10), "#ebcb8b")
        finally:
            canvas.pop_clip()


class CheckboxMorph(Morph):
    """Clickable boolean checkbox with label."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 180,
        height: float = 24,
        label: str = "Option",
        checked: bool = False,
        on_change: Optional[Callable[[bool], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="transparent", border_width=0.0)
        self.label = label
        self.checked = bool(checked)
        self.on_change = on_change

    def toggle(self) -> bool:
        self.checked = not self.checked
        if callable(self.on_change):
            self.on_change(self.checked)
        self.changed()
        return self.checked

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            self.toggle()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        box = min(16.0, max(12.0, self.height - 6.0))
        bx = self.x + 2.0
        by = self.y + (self.height - box) / 2.0
        fill = "#5e81ac" if self.checked else "#1e222a"
        stroke = "#88c0d0" if self.checked else "#4c566a"
        canvas.fill_round_rect(bx, by, box, box, 3.0, fill, stroke, 1.2)
        if self.checked:
            canvas.draw_line(bx + 3.5, by + box * 0.55, bx + box * 0.42, by + box - 3.5, "#eceff4", 2.0)
            canvas.draw_line(bx + box * 0.42, by + box - 3.5, bx + box - 3.0, by + 4.0, "#eceff4", 2.0)
        canvas.draw_text(self.label, bx + box + 8.0, self.y + self.height / 2.0 + 4.5, color="#eceff4", font="12px sans-serif")


class ToggleSwitchMorph(Morph):
    """Pill-shaped on/off toggle switch with optional label."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 160,
        height: float = 24,
        label: str = "",
        checked: bool = False,
        on_change: Optional[Callable[[bool], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="transparent", border_width=0.0)
        self.label = label
        self.checked = bool(checked)
        self.on_change = on_change

    def toggle(self) -> bool:
        self.checked = not self.checked
        if callable(self.on_change):
            self.on_change(self.checked)
        self.changed()
        return self.checked

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            self.toggle()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        sw_w, sw_h = 38.0, 20.0
        sx = self.x + 2.0
        sy = self.y + (self.height - sw_h) / 2.0
        track_col = "#a3be8c" if self.checked else "#3b4252"
        canvas.fill_round_rect(sx, sy, sw_w, sw_h, sw_h / 2.0, track_col, "#4c566a", 1.0)
        knob_r = 7.5
        knob_cx = (sx + sw_w - 10.0) if self.checked else (sx + 10.0)
        canvas.fill_circle(knob_cx, sy + sw_h / 2.0, knob_r, "#eceff4", "#2e3440", 0.8)
        if self.label:
            canvas.draw_text(self.label, sx + sw_w + 8.0, self.y + self.height / 2.0 + 4.5, color="#eceff4", font="12px sans-serif")


class SliderMorph(Morph):
    """Interactive numeric slider supporting horizontal/vertical orientation and step snapping."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 180,
        height: float = 26,
        min_val: float = 0.0,
        max_val: float = 100.0,
        value: float = 50.0,
        step: float = 0.0,
        orientation: str = "horizontal",
        show_value: bool = True,
        on_change: Optional[Callable[[float], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="transparent", border_width=0.0)
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.step = float(step)
        self.orientation = orientation if orientation in ("horizontal", "vertical") else "horizontal"
        self.show_value = show_value
        self.on_change = on_change
        self.value = self._clamp_and_snap(value)
        self._dragging = False

    def _clamp_and_snap(self, v: float) -> float:
        lo, hi = min(self.min_val, self.max_val), max(self.min_val, self.max_val)
        clamped = max(lo, min(hi, float(v)))
        if self.step > 0:
            steps = round((clamped - lo) / self.step)
            clamped = max(lo, min(hi, lo + steps * self.step))
        return clamped

    def set_value(self, value: float, notify: bool = True) -> float:
        new_v = self._clamp_and_snap(value)
        if new_v != self.value:
            self.value = new_v
            if notify and callable(self.on_change):
                self.on_change(self.value)
            self.changed()
        return self.value

    def _track_bounds(self) -> Tuple[float, float, float]:
        if self.orientation == "horizontal":
            label_reserve = 42.0 if self.show_value else 0.0
            tx = self.x + 8.0
            tw = max(20.0, self.width - 16.0 - label_reserve)
            return (tx, self.y + self.height / 2.0, tw)
        ty = self.y + 8.0
        th = max(20.0, self.height - 16.0)
        return (self.x + self.width / 2.0, ty, th)

    def _update_from_point(self, px: float, py: float) -> None:
        span_lo, span_hi = self.min_val, self.max_val
        if span_hi == span_lo:
            return
        if self.orientation == "horizontal":
            tx, _cy, tw = self._track_bounds()
            ratio = max(0.0, min(1.0, (px - tx) / tw))
        else:
            _cx, ty, th = self._track_bounds()
            ratio = max(0.0, min(1.0, 1.0 - (py - ty) / th))
        self.set_value(span_lo + ratio * (span_hi - span_lo), notify=True)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            self._dragging = True
            self._update_from_point(px, py)

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if getattr(self, "_dragging", False):
            self._update_from_point(px, py)

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._dragging = False

    def draw_on(self, canvas: DisplayCanvas) -> None:
        span = self.max_val - self.min_val
        ratio = 0.0 if span == 0 else max(0.0, min(1.0, (self.value - self.min_val) / span))
        if self.orientation == "horizontal":
            tx, cy, tw = self._track_bounds()
            canvas.fill_round_rect(tx, cy - 3.0, tw, 6.0, 3.0, "#2e3440", "#4c566a", 0.8)
            fill_w = max(0.0, tw * ratio)
            if fill_w > 0:
                canvas.fill_round_rect(tx, cy - 3.0, fill_w, 6.0, 3.0, "#88c0d0", "", 0.0)
            kx = tx + fill_w
            canvas.fill_circle(kx, cy, 7.0, "#eceff4", "#5e81ac", 1.5)
            if self.show_value:
                txt = f"{int(round(self.value))}" if self.step >= 1 or float(self.value).is_integer() else f"{self.value:.1f}"
                canvas.draw_text(txt, tx + tw + 10.0, cy + 4.0, color="#d8dee9", font="11px monospace")
        else:
            cx, ty, th = self._track_bounds()
            canvas.fill_round_rect(cx - 3.0, ty, 6.0, th, 3.0, "#2e3440", "#4c566a", 0.8)
            fill_h = max(0.0, th * ratio)
            if fill_h > 0:
                canvas.fill_round_rect(cx - 3.0, ty + th - fill_h, 6.0, fill_h, 3.0, "#88c0d0", "", 0.0)
            ky = ty + th - fill_h
            canvas.fill_circle(cx, ky, 7.0, "#eceff4", "#5e81ac", 1.5)


class DropdownMorph(Morph):
    """Compact selector button that opens a MenuMorph popup to pick an option."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 170,
        height: float = 28,
        options: Optional[List[str]] = None,
        selected_index: int = 0,
        on_change: Optional[Callable[[int, str], Any]] = None,
    ):
        super().__init__(
            x,
            y,
            width,
            height,
            color="#2e3440",
            border_color="#4c566a",
            border_width=1.0,
        )
        self.corner_radius = 4.0
        self.options: List[str] = list(options) if options else ["Option 1"]
        self.selected_index: int = max(0, min(len(self.options) - 1, selected_index))
        self.on_change = on_change

    @property
    def selected_value(self) -> str:
        if 0 <= self.selected_index < len(self.options):
            return self.options[self.selected_index]
        return ""

    def select_index(self, idx: int, notify: bool = True) -> None:
        if 0 <= idx < len(self.options):
            self.selected_index = idx
            if notify and callable(self.on_change):
                self.on_change(idx, self.options[idx])
            self.changed()

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0 or not self.options:
            return
        w = self.world()
        if w is not None:
            items = [
                (opt, (lambda i=idx: self.select_index(i, notify=True)))
                for idx, opt in enumerate(self.options)
            ]
            menu = MenuMorph(self.x, self.y + self.height + 2.0, items)
            menu.width = max(menu.width, self.width)
            w.active_menu = menu
            w.changed()
        else:
            self.select_index((self.selected_index + 1) % len(self.options), notify=True)

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius, self.color, self.border_color, self.border_width
        )
        label = self.selected_value
        max_chars = max(4, int((self.width - 28) // 7.5))
        if len(label) > max_chars:
            label = label[: max_chars - 1] + "…"
        canvas.draw_text(label, self.x + 10.0, self.y + self.height / 2.0 + 4.5, color="#eceff4", font="12px sans-serif")
        # Downward chevron
        cx = self.x + self.width - 14.0
        cy = self.y + self.height / 2.0 - 2.0
        canvas.draw_line(cx - 4.0, cy, cx, cy + 4.5, "#88c0d0", 1.6)
        canvas.draw_line(cx, cy + 4.5, cx + 4.0, cy, "#88c0d0", 1.6)


class ProgressBarMorph(Morph):
    """Determinate (0.0..1.0) or indeterminate animated progress bar."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 200,
        height: float = 20,
        value: float = 0.0,
        indeterminate: bool = False,
        show_label: bool = True,
        bar_color: str = "#88c0d0",
    ):
        super().__init__(x, y, width, height, color="#1b1f27", border_color="#4c566a", border_width=1.0)
        self.corner_radius = 6.0
        self.value = max(0.0, min(1.0, float(value)))
        self.indeterminate = bool(indeterminate)
        self.show_label = show_label
        self.bar_color = bar_color
        self._phase = 0.0

    def set_value(self, value: float) -> None:
        self.value = max(0.0, min(1.0, float(value)))
        self.changed()

    def wants_steps(self) -> bool:
        return self.indeterminate

    def step(self) -> None:
        if self.indeterminate:
            self._phase = (self._phase + 0.03) % 1.0
            self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius, self.color, self.border_color, self.border_width
        )
        inner_w = max(0.0, self.width - 4.0)
        inner_h = max(4.0, self.height - 4.0)
        canvas.push_clip(self.x + 2, self.y + 2, inner_w, inner_h)
        try:
            if self.indeterminate:
                seg_w = max(24.0, inner_w * 0.28)
                sx = self.x + 2 + (inner_w + seg_w) * self._phase - seg_w
                canvas.fill_round_rect(sx, self.y + 2, seg_w, inner_h, 4.0, self.bar_color, "", 0.0)
            else:
                fill_w = inner_w * self.value
                if fill_w > 1.0:
                    canvas.fill_round_rect(self.x + 2, self.y + 2, fill_w, inner_h, 4.0, self.bar_color, "", 0.0)
        finally:
            canvas.pop_clip()

        if self.show_label and not self.indeterminate:
            pct = f"{int(round(self.value * 100))}%"
            tw = canvas.measure_text(pct, "bold 11px monospace")
            canvas.draw_text(pct, self.x + (self.width - tw) / 2.0, self.y + self.height / 2.0 + 4.0, color="#eceff4", font="bold 11px monospace")


class ImageMorph(Morph):
    """Displays a Form bitmap cleanly with contain, stretch, or center fit."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 96,
        height: float = 96,
        form: Optional[Form] = None,
        fit: str = "contain",
    ):
        super().__init__(x, y, width, height, color="#14171d", border_color="#4c566a", border_width=1.0)
        self.form = form
        self.fit = fit if fit in ("contain", "stretch", "center") else "contain"

    def set_form(self, form: Optional[Form]) -> None:
        self.form = form
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(self.x, self.y, self.width, self.height, 4.0, self.color, self.border_color, self.border_width)
        if self.form is None or self.form.width <= 0 or self.form.height <= 0:
            canvas.draw_text("No Form", self.x + 8, self.y + self.height / 2.0 + 4, color="#616e88", font="11px monospace")
            return
        canvas.push_clip(self.x + 2, self.y + 2, max(2.0, self.width - 4), max(2.0, self.height - 4))
        try:
            fx = self.x + max(2.0, (self.width - self.form.width) / 2.0)
            fy = self.y + max(2.0, (self.height - self.form.height) / 2.0)
            canvas.blit_form(self.form, fx, fy)
        finally:
            canvas.pop_clip()


class TableMorph(Morph):
    """Multi-column sortable data table with vertical scrolling and row selection."""

    HEADER_HEIGHT = 24.0
    ROW_HEIGHT = 22.0
    SCROLLBAR_WIDTH = 12.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 320,
        height: float = 180,
        columns: Optional[List[str]] = None,
        rows: Optional[List[List[Any]]] = None,
        on_select: Optional[Callable[[int, List[Any]], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="#1b1f27", border_color="#4c566a", border_width=1.0)
        self.columns: List[str] = list(columns) if columns else ["Column"]
        self.rows: List[List[Any]] = [list(r) for r in (rows or [])]
        self.on_select = on_select
        self.selected_row: int = -1
        self.scroll_offset: int = 0
        self.sort_col: Optional[int] = None
        self.sort_asc: bool = True
        self._dragging_sb: bool = False
        self._drag_offset: float = 0.0

    def set_rows(self, rows: List[List[Any]]) -> None:
        self.rows = [list(r) for r in rows]
        self.selected_row = -1
        self.scroll_offset = 0
        self.changed()

    def _visible_rows(self) -> int:
        return max(1, int((self.height - self.HEADER_HEIGHT - 2.0) // self.ROW_HEIGHT))

    def _max_scroll(self) -> int:
        return max(0, len(self.rows) - self._visible_rows())

    def _scrollbar_geometry(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        total = len(self.rows)
        vis = self._visible_rows()
        if total <= vis:
            return None
        tx = self.x + self.width - self.SCROLLBAR_WIDTH - 1.0
        ty = self.y + self.HEADER_HEIGHT + 1.0
        th = max(16.0, self.height - self.HEADER_HEIGHT - 2.0)
        thumb_h = max(18.0, min(th, th * (vis / float(total))))
        ratio = max(0.0, min(1.0, self.scroll_offset / float(max(1, total - vis))))
        thumb_y = ty + ratio * (th - thumb_h)
        return (tx, ty, self.SCROLLBAR_WIDTH, th, thumb_y, thumb_h)

    def sort_by_column(self, col_idx: int) -> None:
        if not (0 <= col_idx < len(self.columns)):
            return
        if self.sort_col == col_idx:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col_idx
            self.sort_asc = True
        self.rows.sort(
            key=lambda r: str(r[col_idx]) if col_idx < len(r) else "",
            reverse=not self.sort_asc,
        )
        self.selected_row = -1
        self.changed()

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        sb = self._scrollbar_geometry()
        if sb is not None and px >= sb[0] and py >= sb[1]:
            _tx, ty, _tw, th, thumb_y, thumb_h = sb
            if thumb_y <= py <= thumb_y + thumb_h:
                self._dragging_sb = True
                self._drag_offset = py - thumb_y
            elif py < thumb_y:
                self.scroll_offset = max(0, self.scroll_offset - self._visible_rows())
            else:
                self.scroll_offset = min(self._max_scroll(), self.scroll_offset + self._visible_rows())
            self.changed()
            return

        if py <= self.y + self.HEADER_HEIGHT:
            avail_w = self.width - (self.SCROLLBAR_WIDTH if sb is not None else 0.0)
            col_w = max(20.0, avail_w / max(1, len(self.columns)))
            col_idx = int((px - self.x) // col_w)
            self.sort_by_column(col_idx)
            return

        row_idx = int((py - (self.y + self.HEADER_HEIGHT)) // self.ROW_HEIGHT) + self.scroll_offset
        if 0 <= row_idx < len(self.rows):
            self.selected_row = row_idx
            if callable(self.on_select):
                self.on_select(row_idx, self.rows[row_idx])
            self.changed()

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if getattr(self, "_dragging_sb", False):
            sb = self._scrollbar_geometry()
            if sb is not None:
                _tx, ty, _tw, th, _thumb_y, thumb_h = sb
                ratio = max(0.0, min(1.0, (py - self._drag_offset - ty) / max(1.0, th - thumb_h)))
                self.scroll_offset = int(round(ratio * self._max_scroll()))
                self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._dragging_sb = False

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if delta_y == 0:
            return
        step = max(1, min(4, int(round(abs(delta_y) / 25.0))))
        self.scroll_offset = max(0, min(self._max_scroll(), self.scroll_offset + (step if delta_y > 0 else -step)))
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        sb = self._scrollbar_geometry()
        avail_w = self.width - (self.SCROLLBAR_WIDTH if sb is not None else 0.0)
        col_w = max(20.0, avail_w / max(1, len(self.columns)))

        # Header
        canvas.fill_rect(self.x + 1, self.y + 1, avail_w - 2, self.HEADER_HEIGHT - 1, "#252b37")
        for ci, col_name in enumerate(self.columns):
            cx = self.x + ci * col_w
            arrow = ""
            if self.sort_col == ci:
                arrow = " ▲" if self.sort_asc else " ▼"
            canvas.draw_text(f"{col_name}{arrow}", cx + 8.0, self.y + 16.0, color="#88c0d0", font="bold 11px sans-serif")
            if ci > 0:
                canvas.draw_line(cx, self.y + 2, cx, self.y + self.height - 2, "#2e3440", 1.0)
        canvas.draw_line(self.x + 1, self.y + self.HEADER_HEIGHT, self.x + avail_w - 1, self.y + self.HEADER_HEIGHT, "#4c566a", 1.0)

        canvas.push_clip(self.x + 1, self.y + self.HEADER_HEIGHT + 1, avail_w - 2, max(4.0, self.height - self.HEADER_HEIGHT - 2))
        try:
            vis = self._visible_rows() + 1
            for i in range(vis):
                r_idx = self.scroll_offset + i
                if r_idx >= len(self.rows):
                    break
                ry = self.y + self.HEADER_HEIGHT + i * self.ROW_HEIGHT
                is_sel = r_idx == self.selected_row
                if is_sel:
                    canvas.fill_rect(self.x + 1, ry, avail_w - 2, self.ROW_HEIGHT, "#5e81ac")
                elif i % 2 == 1:
                    canvas.fill_rect(self.x + 1, ry, avail_w - 2, self.ROW_HEIGHT, "#1f242e")
                row = self.rows[r_idx]
                max_chars = max(3, int((col_w - 12) // 7.2))
                for ci in range(len(self.columns)):
                    val = str(row[ci]) if ci < len(row) else ""
                    if len(val) > max_chars:
                        val = val[: max_chars - 1] + "…"
                    canvas.draw_text(val, self.x + ci * col_w + 8.0, ry + 15.0, color="#ffffff" if is_sel else "#d8dee9", font="12px monospace")
        finally:
            canvas.pop_clip()

        if sb is not None:
            tx, ty, tw, th, thumb_y, thumb_h = sb
            canvas.fill_rect(tx, ty, tw, th, "#14171d")
            canvas.fill_round_rect(tx + 2, thumb_y, tw - 4, thumb_h, 3.0, "#4c566a", "", 0.0)


class TreeMorph(Morph):
    """Expandable hierarchical tree view with node selection and scrolling."""

    ROW_HEIGHT = 22.0
    SCROLLBAR_WIDTH = 12.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 220,
        height: float = 180,
        nodes: Optional[List[Dict[str, Any]]] = None,
        on_select: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="#1b1f27", border_color="#4c566a", border_width=1.0)
        self.nodes: List[Dict[str, Any]] = list(nodes) if nodes else []
        self.on_select = on_select
        self.selected_node: Optional[Dict[str, Any]] = None
        self.scroll_offset: int = 0

    def _flat_visible(self) -> List[Tuple[Dict[str, Any], int]]:
        out: List[Tuple[Dict[str, Any], int]] = []

        def visit(items: List[Dict[str, Any]], depth: int) -> None:
            for node in items:
                out.append((node, depth))
                if node.get("expanded") and node.get("children"):
                    visit(node["children"], depth + 1)

        visit(self.nodes, 0)
        return out

    def _visible_rows(self) -> int:
        return max(1, int((self.height - 4.0) // self.ROW_HEIGHT))

    def _max_scroll(self) -> int:
        return max(0, len(self._flat_visible()) - self._visible_rows())

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        flat = self._flat_visible()
        idx = int((py - (self.y + 2.0)) // self.ROW_HEIGHT) + self.scroll_offset
        if 0 <= idx < len(flat):
            node, depth = flat[idx]
            tri_x = self.x + 8.0 + depth * 16.0
            if node.get("children") and px <= tri_x + 16.0:
                node["expanded"] = not bool(node.get("expanded"))
            self.selected_node = node
            if callable(self.on_select):
                self.on_select(node)
            self.scroll_offset = min(self.scroll_offset, self._max_scroll())
            self.changed()

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if delta_y == 0:
            return
        step = max(1, min(4, int(round(abs(delta_y) / 25.0))))
        self.scroll_offset = max(0, min(self._max_scroll(), self.scroll_offset + (step if delta_y > 0 else -step)))
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        flat = self._flat_visible()
        canvas.push_clip(self.x + 1, self.y + 1, max(4.0, self.width - 2), max(4.0, self.height - 2))
        try:
            vis = self._visible_rows() + 1
            for i in range(vis):
                idx = self.scroll_offset + i
                if idx >= len(flat):
                    break
                node, depth = flat[idx]
                ry = self.y + 2.0 + i * self.ROW_HEIGHT
                is_sel = node is self.selected_node
                if is_sel:
                    canvas.fill_rect(self.x + 1, ry, self.width - 2, self.ROW_HEIGHT, "#5e81ac")
                indent_x = self.x + 8.0 + depth * 16.0
                if node.get("children"):
                    glyph = "▼" if node.get("expanded") else "▶"
                    canvas.draw_text(glyph, indent_x, ry + 15.0, color="#88c0d0", font="10px sans-serif")
                else:
                    canvas.draw_text("•", indent_x + 2.0, ry + 15.0, color="#616e88", font="11px monospace")
                label = str(node.get("label", ""))
                canvas.draw_text(label, indent_x + 15.0, ry + 15.0, color="#ffffff" if is_sel else "#eceff4", font="12px sans-serif")
        finally:
            canvas.pop_clip()


class DialogMorph(Morph):
    """Centered modal dialog with message, optional TextInputMorph, and action buttons."""

    def __init__(
        self,
        title: str = "Dialog",
        message: str = "",
        buttons: Optional[List[Tuple[str, Optional[Callable[..., Any]]]]] = None,
        input_default: Optional[str] = None,
        width: float = 360,
        height: float = 170,
    ):
        if input_default is not None and height < 190:
            height = 195
        super().__init__(0, 0, width, height, color="#242933", border_color="#88c0d0", border_width=1.8)
        self.corner_radius = 8.0
        self.title = title
        self.message = message
        self.input_field: Optional[TextInputMorph] = None
        if input_default is not None:
            self.input_field = TextInputMorph(
                18, 92, width - 36, 28, text=input_default, placeholder="Enter value..."
            )
            self.add_morph(self.input_field)

        btn_specs = buttons if buttons else [("OK", None)]
        bw = 88.0
        gap = 10.0
        total_bw = len(btn_specs) * bw + max(0, len(btn_specs) - 1) * gap
        bx = (width - total_bw) / 2.0
        by = height - 42.0
        for idx, (label, cb) in enumerate(btn_specs):
            btn = ButtonMorph(
                label,
                x=bx + idx * (bw + gap),
                y=by,
                width=bw,
                height=26.0,
                on_click=lambda c=cb: self._handle_button(c),
                color="#5e81ac" if idx == 0 else "#3b4252",
            )
            self.add_morph(btn)

    def _handle_button(self, cb: Optional[Callable[..., Any]]) -> None:
        val = self.input_field.text if self.input_field is not None else None
        w = self.world()
        if w is not None and hasattr(w, "close_modal"):
            w.close_modal()
        if callable(cb):
            if val is not None:
                try:
                    cb(val)
                except TypeError:
                    cb()
            else:
                cb()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius, self.color, self.border_color, self.border_width
        )
        canvas.fill_round_rect(self.x + 1, self.y + 1, self.width - 2, 28.0, 6.0, "#1e222a", "", 0.0)
        canvas.draw_text(self.title, self.x + 14.0, self.y + 19.0, color="#eceff4", font="bold 13px sans-serif")
        for li, line in enumerate(self.message.split("\n")[:3]):
            canvas.draw_text(line, self.x + 18.0, self.y + 52.0 + li * 18.0, color="#d8dee9", font="12px sans-serif")
