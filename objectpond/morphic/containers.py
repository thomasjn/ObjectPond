from typing import Any, Callable, Dict, List, Optional, Tuple
from objectpond.morphic.canvas import DisplayCanvas
from objectpond.morphic.morph import Morph


def _place_morph(m: Morph, nx: float, ny: float, nw: Optional[float] = None, nh: Optional[float] = None) -> None:
    """Repositions a Morph in world coordinates (translating submorphs) and optionally resizes it."""
    dx = nx - m.x
    dy = ny - m.y
    if dx != 0.0 or dy != 0.0:
        m.move_by(dx, dy)
    if nw is not None or nh is not None:
        tw = m.width if nw is None else max(1.0, nw)
        th = m.height if nh is None else max(1.0, nh)
        if tw != m.width or th != m.height:
            m.set_extent(tw, th)


class LayoutMorph(Morph):
    """Flex-like row/column container that positions and sizes child morphs automatically."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 300,
        height: float = 200,
        direction: str = "column",
        padding: float = 8.0,
        spacing: float = 8.0,
        align: str = "stretch",
        color: str = "transparent",
        border_color: str = "transparent",
        border_width: float = 0.0,
    ):
        super().__init__(x, y, width, height, color=color, border_color=border_color, border_width=border_width)
        self.direction = direction if direction in ("row", "column") else "column"
        self.padding = float(padding)
        self.spacing = float(spacing)
        self.align = align if align in ("start", "center", "stretch") else "stretch"
        self._flex_weights: Dict[int, float] = {}

    def add_child(self, morph: Morph, flex: float = 0.0) -> Morph:
        self.add_morph(morph)
        if flex > 0:
            self._flex_weights[id(morph)] = float(flex)
        self.relayout()
        return morph

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self.relayout()

    def relayout(self) -> None:
        children = [m for m in self.submorphs if m.visible]
        if not children:
            return
        is_row = self.direction == "row"
        inner_x = self.x + self.padding
        inner_y = self.y + self.padding
        inner_w = max(4.0, self.width - 2.0 * self.padding)
        inner_h = max(4.0, self.height - 2.0 * self.padding)
        total_gap = self.spacing * max(0, len(children) - 1)

        total_main = inner_w if is_row else inner_h
        fixed_sum = 0.0
        flex_sum = 0.0
        for c in children:
            fw = self._flex_weights.get(id(c), 0.0)
            if fw > 0:
                flex_sum += fw
            else:
                fixed_sum += c.width if is_row else c.height

        avail_flex = max(0.0, total_main - total_gap - fixed_sum)
        cursor = inner_x if is_row else inner_y

        for c in children:
            fw = self._flex_weights.get(id(c), 0.0)
            if is_row:
                cw = (avail_flex * (fw / flex_sum)) if (fw > 0 and flex_sum > 0) else c.width
                ch = inner_h if self.align == "stretch" else min(c.height, inner_h)
                cy = inner_y + ((inner_h - ch) / 2.0 if self.align == "center" else 0.0)
                _place_morph(c, cursor, cy, cw, ch)
                cursor += cw + self.spacing
            else:
                ch = (avail_flex * (fw / flex_sum)) if (fw > 0 and flex_sum > 0) else c.height
                cw = inner_w if self.align == "stretch" else min(c.width, inner_w)
                cx = inner_x + ((inner_w - cw) / 2.0 if self.align == "center" else 0.0)
                _place_morph(c, cx, cursor, cw, ch)
                cursor += ch + self.spacing
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        if self.color != "transparent":
            canvas.fill_round_rect(
                self.x, self.y, self.width, self.height, self.corner_radius, self.color, self.border_color, self.border_width
            )


class RowMorph(LayoutMorph):
    """Horizontal LayoutMorph convenience subclass."""

    def __init__(self, x: float = 0, y: float = 0, width: float = 300, height: float = 40, **kwargs: Any):
        kwargs["direction"] = "row"
        super().__init__(x, y, width, height, **kwargs)


class ColumnMorph(LayoutMorph):
    """Vertical LayoutMorph convenience subclass."""

    def __init__(self, x: float = 0, y: float = 0, width: float = 240, height: float = 240, **kwargs: Any):
        kwargs["direction"] = "column"
        super().__init__(x, y, width, height, **kwargs)


class ScrollPaneMorph(Morph):
    """Scrollable viewport container clipping a child Morph with vertical and conditional horizontal scrollbars."""

    SCROLLBAR_WIDTH = 12.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 300,
        height: float = 220,
        content: Optional[Morph] = None,
    ):
        super().__init__(x, y, width, height, color="#1b1f27", border_color="#4c566a", border_width=1.0)
        self.content: Optional[Morph] = None
        self.scroll_x: float = 0.0
        self.scroll_y: float = 0.0
        self._dragging_vsb: bool = False
        self._dragging_hsb: bool = False
        self._drag_offset: float = 0.0
        if content is not None:
            self.set_content(content)

    def set_content(self, morph: Morph) -> Morph:
        for s in list(self.submorphs):
            s.delete()
        self.content = morph
        self.scroll_x = 0.0
        self.scroll_y = 0.0
        self.add_morph(morph)
        self._sync_content_position()
        self.changed()
        return morph

    def _max_scroll_x(self) -> float:
        if self.content is None:
            return 0.0
        vw = max(10.0, self.width - self.SCROLLBAR_WIDTH - 2.0)
        return max(0.0, self.content.width - vw)

    def _max_scroll_y(self) -> float:
        if self.content is None:
            return 0.0
        h_res = self.SCROLLBAR_WIDTH if self._max_scroll_x() > 0 else 0.0
        vh = max(10.0, self.height - h_res - 2.0)
        return max(0.0, self.content.height - vh)

    def _sync_content_position(self) -> None:
        self.scroll_x = max(0.0, min(self._max_scroll_x(), self.scroll_x))
        self.scroll_y = max(0.0, min(self._max_scroll_y(), self.scroll_y))
        if self.content is not None:
            _place_morph(self.content, self.x + 2.0 - self.scroll_x, self.y + 2.0 - self.scroll_y)

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self._sync_content_position()

    def _vsb_geometry(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        max_y = self._max_scroll_y()
        if max_y <= 0 or self.content is None:
            return None
        h_res = self.SCROLLBAR_WIDTH if self._max_scroll_x() > 0 else 0.0
        tx = self.x + self.width - self.SCROLLBAR_WIDTH - 1.0
        ty = self.y + 1.0
        th = max(20.0, self.height - 2.0 - h_res)
        vh = max(10.0, self.height - 2.0 - h_res)
        thumb_h = max(20.0, min(th, th * (vh / max(1.0, self.content.height))))
        thumb_y = ty + (self.scroll_y / max_y) * (th - thumb_h)
        return (tx, ty, self.SCROLLBAR_WIDTH, th, thumb_y, thumb_h)

    def _hsb_geometry(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        max_x = self._max_scroll_x()
        if max_x <= 0 or self.content is None:
            return None
        v_res = self.SCROLLBAR_WIDTH if self._max_scroll_y() > 0 else 0.0
        tx = self.x + 1.0
        ty = self.y + self.height - self.SCROLLBAR_WIDTH - 1.0
        tw = max(20.0, self.width - 2.0 - v_res)
        vw = max(10.0, self.width - 2.0 - v_res)
        thumb_w = max(20.0, min(tw, tw * (vw / max(1.0, self.content.width))))
        thumb_x = tx + (self.scroll_x / max_x) * (tw - thumb_w)
        return (tx, ty, tw, self.SCROLLBAR_WIDTH, thumb_x, thumb_w)

    def morph_at(self, px: float, py: float) -> Optional[Morph]:
        if not self.visible or not self.contains_point(px, py):
            return None
        vsb = self._vsb_geometry()
        if vsb is not None and px >= vsb[0] and py <= vsb[1] + vsb[3]:
            return self
        hsb = self._hsb_geometry()
        if hsb is not None and py >= hsb[1] and px <= hsb[0] + hsb[2]:
            return self
        return super().morph_at(px, py)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        vsb = self._vsb_geometry()
        if vsb is not None and px >= vsb[0] and py <= vsb[1] + vsb[3]:
            _tx, ty, _tw, th, thumb_y, thumb_h = vsb
            if thumb_y <= py <= thumb_y + thumb_h:
                self._dragging_vsb = True
                self._drag_offset = py - thumb_y
            elif py < thumb_y:
                self.scroll_y -= th * 0.8
            else:
                self.scroll_y += th * 0.8
            self._sync_content_position()
            self.changed()
            return

        hsb = self._hsb_geometry()
        if hsb is not None and py >= hsb[1] and px <= hsb[0] + hsb[2]:
            tx, _ty, tw, _th, thumb_x, thumb_w = hsb
            if thumb_x <= px <= thumb_x + thumb_w:
                self._dragging_hsb = True
                self._drag_offset = px - thumb_x
            elif px < thumb_x:
                self.scroll_x -= tw * 0.8
            else:
                self.scroll_x += tw * 0.8
            self._sync_content_position()
            self.changed()

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if getattr(self, "_dragging_vsb", False):
            vsb = self._vsb_geometry()
            if vsb is not None:
                _tx, ty, _tw, th, _thumb_y, thumb_h = vsb
                ratio = max(0.0, min(1.0, (py - self._drag_offset - ty) / max(1.0, th - thumb_h)))
                self.scroll_y = ratio * self._max_scroll_y()
                self._sync_content_position()
                self.changed()
        elif getattr(self, "_dragging_hsb", False):
            hsb = self._hsb_geometry()
            if hsb is not None:
                tx, _ty, tw, _th, _thumb_x, thumb_w = hsb
                ratio = max(0.0, min(1.0, (px - self._drag_offset - tx) / max(1.0, tw - thumb_w)))
                self.scroll_x = ratio * self._max_scroll_x()
                self._sync_content_position()
                self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._dragging_vsb = False
        self._dragging_hsb = False

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if delta_y != 0:
            self.scroll_y += delta_y * 0.5
            self._sync_content_position()
            self.changed()

    def full_draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, self.border_width)
        vsb = self._vsb_geometry()
        hsb = self._hsb_geometry()
        clip_w = max(4.0, self.width - 2.0 - (self.SCROLLBAR_WIDTH if vsb is not None else 0.0))
        clip_h = max(4.0, self.height - 2.0 - (self.SCROLLBAR_WIDTH if hsb is not None else 0.0))
        canvas.push_clip(self.x + 1.0, self.y + 1.0, clip_w, clip_h)
        try:
            for sub in self.submorphs:
                if sub.visible:
                    sub.full_draw_on(canvas)
        finally:
            canvas.pop_clip()

        if vsb is not None:
            tx, ty, tw, th, thumb_y, thumb_h = vsb
            canvas.fill_rect(tx, ty, tw, th, "#14171d")
            canvas.fill_round_rect(tx + 2, thumb_y, tw - 4, thumb_h, 3.0, "#4c566a", "", 0.0)
        if hsb is not None:
            tx, ty, tw, th, thumb_x, thumb_w = hsb
            canvas.fill_rect(tx, ty, tw, th, "#14171d")
            canvas.fill_round_rect(thumb_x, ty + 2, thumb_w, th - 4, 3.0, "#4c566a", "", 0.0)
        self.is_damaged = False


class TabViewMorph(Morph):
    """Tabbed container switching between labeled child panes."""

    TAB_HEIGHT = 28.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 400,
        height: float = 280,
        tabs: Optional[List[Tuple[str, Morph]]] = None,
        active_index: int = 0,
        on_tab_change: Optional[Callable[[int], Any]] = None,
    ):
        super().__init__(x, y, width, height, color="#1e222a", border_color="#4c566a", border_width=1.0)
        self.tabs: List[Tuple[str, Morph]] = []
        self.active_index: int = 0
        self.on_tab_change = on_tab_change
        for title, pane in (tabs or []):
            self.add_tab(title, pane)
        if self.tabs:
            self.select_tab(active_index, notify=False)

    def add_tab(self, title: str, pane: Morph) -> None:
        self.tabs.append((title, pane))
        self.add_morph(pane)
        self._layout_panes()

    def select_tab(self, idx: int, notify: bool = True) -> None:
        if not (0 <= idx < len(self.tabs)):
            return
        self.active_index = idx
        self._layout_panes()
        if notify and callable(self.on_tab_change):
            self.on_tab_change(idx)
        self.changed()

    def _layout_panes(self) -> None:
        px = self.x + 2.0
        py = self.y + self.TAB_HEIGHT + 2.0
        pw = max(20.0, self.width - 4.0)
        ph = max(20.0, self.height - self.TAB_HEIGHT - 4.0)
        for idx, (_title, pane) in enumerate(self.tabs):
            pane.visible = idx == self.active_index
            if pane.visible:
                _place_morph(pane, px, py, pw, ph)

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self._layout_panes()

    def _tab_width(self) -> float:
        return min(150.0, max(64.0, (self.width - 8.0) / max(1, len(self.tabs))))

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0 and py <= self.y + self.TAB_HEIGHT:
            tw = self._tab_width()
            idx = int((px - (self.x + 4.0)) // tw)
            if 0 <= idx < len(self.tabs):
                self.select_tab(idx, notify=True)

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        canvas.fill_rect(self.x + 1, self.y + 1, self.width - 2, self.TAB_HEIGHT - 1, "#181c23")
        tw = self._tab_width()
        for idx, (title, _pane) in enumerate(self.tabs):
            tx = self.x + 4.0 + idx * tw
            is_act = idx == self.active_index
            fill = "#2e3440" if is_act else "#1b2028"
            canvas.fill_round_rect(tx, self.y + 3.0, tw - 4.0, self.TAB_HEIGHT - 4.0, 4.0, fill, "#5e81ac" if is_act else "#2e3440", 1.0)
            canvas.draw_text(title, tx + 10.0, self.y + 19.0, color="#88c0d0" if is_act else "#9aa5b8", font="bold 11px sans-serif" if is_act else "11px sans-serif")


class SplitPaneMorph(Morph):
    """Two-pane container with a draggable horizontal or vertical divider."""

    SPLITTER_SIZE = 6.0

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 400,
        height: float = 240,
        first: Optional[Morph] = None,
        second: Optional[Morph] = None,
        orientation: str = "horizontal",
        ratio: float = 0.4,
        min_pane_size: float = 60.0,
    ):
        super().__init__(x, y, width, height, color="#1e222a", border_color="#4c566a", border_width=1.0)
        self.orientation = orientation if orientation in ("horizontal", "vertical") else "horizontal"
        self.ratio = max(0.1, min(0.9, float(ratio)))
        self.min_pane_size = float(min_pane_size)
        self.first = first
        self.second = second
        self._dragging_splitter = False
        if first is not None:
            self.add_morph(first)
        if second is not None:
            self.add_morph(second)
        self._layout_panes()

    def _splitter_rect(self) -> Tuple[float, float, float, float]:
        if self.orientation == "horizontal":
            avail = max(20.0, self.width - self.SPLITTER_SIZE - 4.0)
            first_w = max(self.min_pane_size, min(avail - self.min_pane_size, avail * self.ratio))
            return (self.x + 2.0 + first_w, self.y + 2.0, self.SPLITTER_SIZE, max(10.0, self.height - 4.0))
        avail = max(20.0, self.height - self.SPLITTER_SIZE - 4.0)
        first_h = max(self.min_pane_size, min(avail - self.min_pane_size, avail * self.ratio))
        return (self.x + 2.0, self.y + 2.0 + first_h, max(10.0, self.width - 4.0), self.SPLITTER_SIZE)

    def _layout_panes(self) -> None:
        sx, sy, sw, sh = self._splitter_rect()
        if self.orientation == "horizontal":
            first_w = max(10.0, sx - (self.x + 2.0))
            second_x = sx + sw
            second_w = max(10.0, (self.x + self.width - 2.0) - second_x)
            pane_h = max(10.0, self.height - 4.0)
            if self.first is not None:
                _place_morph(self.first, self.x + 2.0, self.y + 2.0, first_w, pane_h)
            if self.second is not None:
                _place_morph(self.second, second_x, self.y + 2.0, second_w, pane_h)
        else:
            first_h = max(10.0, sy - (self.y + 2.0))
            second_y = sy + sh
            second_h = max(10.0, (self.y + self.height - 2.0) - second_y)
            pane_w = max(10.0, self.width - 4.0)
            if self.first is not None:
                _place_morph(self.first, self.x + 2.0, self.y + 2.0, pane_w, first_h)
            if self.second is not None:
                _place_morph(self.second, self.x + 2.0, second_y, pane_w, second_h)

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self._layout_panes()

    def morph_at(self, px: float, py: float) -> Optional[Morph]:
        if not self.visible or not self.contains_point(px, py):
            return None
        sx, sy, sw, sh = self._splitter_rect()
        if sx - 2.0 <= px <= sx + sw + 2.0 and sy - 2.0 <= py <= sy + sh + 2.0:
            return self
        return super().morph_at(px, py)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            sx, sy, sw, sh = self._splitter_rect()
            if sx - 2.0 <= px <= sx + sw + 2.0 and sy - 2.0 <= py <= sy + sh + 2.0:
                self._dragging_splitter = True

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if getattr(self, "_dragging_splitter", False):
            if self.orientation == "horizontal":
                avail = max(20.0, self.width - self.SPLITTER_SIZE - 4.0)
                self.ratio = max(0.1, min(0.9, (px - (self.x + 2.0)) / avail))
            else:
                avail = max(20.0, self.height - self.SPLITTER_SIZE - 4.0)
                self.ratio = max(0.1, min(0.9, (py - (self.y + 2.0)) / avail))
            self._layout_panes()
            self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._dragging_splitter = False

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        sx, sy, sw, sh = self._splitter_rect()
        canvas.fill_rect(sx, sy, sw, sh, "#3b4252")
