from typing import Any, Callable, Dict, List, Optional, Tuple
from objectpond.morphic.app_widgets import (
    CheckboxMorph,
    DropdownMorph,
    ProgressBarMorph,
    SliderMorph,
    TableMorph,
    TextInputMorph,
    ToggleSwitchMorph,
    TreeMorph,
)
from objectpond.morphic.canvas import DisplayCanvas
from objectpond.morphic.morph import Morph
from objectpond.morphic.widgets import (
    ButtonMorph,
    CodeEditorMorph,
    LabelMorph,
    ListMorph,
    SystemWindowMorph,
)


WIDGET_SPECS: List[Tuple[str, float, float, str]] = [
    ("LabelMorph", 140.0, 24.0, "Label"),
    ("ButtonMorph", 110.0, 28.0, "Click Me"),
    ("TextInputMorph", 180.0, 28.0, ""),
    ("CheckboxMorph", 150.0, 24.0, "Enabled"),
    ("ToggleSwitchMorph", 150.0, 24.0, "Active"),
    ("SliderMorph", 180.0, 26.0, ""),
    ("DropdownMorph", 160.0, 28.0, "Option A"),
    ("ProgressBarMorph", 180.0, 22.0, ""),
    ("ListMorph", 160.0, 110.0, ""),
    ("TableMorph", 240.0, 120.0, ""),
    ("TreeMorph", 180.0, 120.0, ""),
    ("CodeEditorMorph", 220.0, 120.0, "# code"),
]

BIND_TARGETS = ["Instance (self.attr)", "Class (cls.attr)", "Global (World)"]


def _snap_val(val: float, grid: float, enabled: bool) -> float:
    if not enabled or grid <= 0:
        return round(val, 1)
    return round(val / grid) * grid


def _sanitize_ident(name: str, fallback: str) -> str:
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in str(name).strip())
    if not cleaned or cleaned[0].isdigit():
        return fallback
    return cleaned


class _DesignPaletteMorph(Morph):
    """Draggable widget palette for AppBuilderWindow."""

    ROW_H = 24.0

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        builder: "AppBuilderWindow",
    ):
        super().__init__(x, y, width, height, color="#1b1f27", border_color="#4c566a", border_width=1.0)
        self.builder = builder
        self._pressed_idx: int = -1
        self._start_x: float = 0.0
        self._start_y: float = 0.0
        self._dragging_kind: Optional[str] = None
        self._drag_px: float = 0.0
        self._drag_py: float = 0.0

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        idx = int((py - (self.y + 24.0)) // self.ROW_H)
        if 0 <= idx < len(WIDGET_SPECS):
            self._pressed_idx = idx
            self._start_x = px
            self._start_y = py
            self._dragging_kind = None

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if self._pressed_idx < 0:
            return
        if abs(px - self._start_x) > 5.0 or abs(py - self._start_y) > 5.0:
            self._dragging_kind = WIDGET_SPECS[self._pressed_idx][0]
            self._drag_px = px
            self._drag_py = py
            self.builder.set_palette_drag(self._dragging_kind, px, py)

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        if self._pressed_idx < 0:
            return
        kind = WIDGET_SPECS[self._pressed_idx][0]
        was_dragging = self._dragging_kind is not None
        self._pressed_idx = -1
        self._dragging_kind = None
        self.builder.clear_palette_drag()
        if was_dragging:
            self.builder.drop_palette_widget(kind, px, py)
        else:
            self.builder.add_widget_from_palette(kind)

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        canvas.fill_rect(self.x + 1, self.y + 1, self.width - 2, 22.0, "#252b37")
        canvas.draw_text("Widgets (Drag/Click)", self.x + 8.0, self.y + 16.0, color="#88c0d0", font="bold 11px sans-serif")
        canvas.push_clip(self.x + 1, self.y + 23, max(4.0, self.width - 2), max(4.0, self.height - 24))
        try:
            for idx, (kind, _w, _h, _lbl) in enumerate(WIDGET_SPECS):
                ry = self.y + 24.0 + idx * self.ROW_H
                if ry > self.y + self.height:
                    break
                fill = "#2e3440" if idx == self._pressed_idx else ("#1f242e" if idx % 2 == 1 else "#1b1f27")
                canvas.fill_rect(self.x + 2, ry, self.width - 4, self.ROW_H - 1, fill)
                short = kind.replace("Morph", "")
                canvas.draw_text(f"+ {short}", self.x + 8.0, ry + 16.0, color="#eceff4", font="11px monospace")
        finally:
            canvas.pop_clip()


class _DesignCanvasMorph(Morph):
    """Interactive visual design surface with grid snapping, smart alignment guides, and resize handles."""

    GRID_SIZE = 10.0
    SNAP_TOL = 6.0
    HANDLE_SIZE = 8.0

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        builder: "AppBuilderWindow",
    ):
        super().__init__(x, y, width, height, color="#161a22", border_color="#4c566a", border_width=1.0)
        self.builder = builder
        self.items: List[Dict[str, Any]] = []
        self.selected_index: int = -1
        self.snap_grid: bool = True
        self.smart_guides: bool = True
        self._drag_mode: Optional[str] = None  # "move" or corner "nw"|"ne"|"sw"|"se"
        self._drag_start_px: float = 0.0
        self._drag_start_py: float = 0.0
        self._orig_rect: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.active_vguides: List[float] = []
        self.active_hguides: List[float] = []

    def _build_preview_morph(self, item: Dict[str, Any]) -> Morph:
        kind = item["kind"]
        rx = self.x + item["x"]
        ry = self.y + item["y"]
        w = item["width"]
        h = item["height"]
        lbl = item.get("label", "")
        if kind == "LabelMorph":
            m = LabelMorph(lbl or "Label", rx, ry, color="#eceff4")
            m.width, m.height = w, h
            return m
        if kind == "ButtonMorph":
            return ButtonMorph(lbl or "Button", rx, ry, w, h)
        if kind == "TextInputMorph":
            return TextInputMorph(rx, ry, w, h, text=lbl, placeholder="TextInput...")
        if kind == "CheckboxMorph":
            return CheckboxMorph(rx, ry, w, h, label=lbl or "Option", checked=True)
        if kind == "ToggleSwitchMorph":
            return ToggleSwitchMorph(rx, ry, w, h, label=lbl or "Toggle", checked=True)
        if kind == "SliderMorph":
            return SliderMorph(rx, ry, w, h, min_val=0, max_val=100, value=50)
        if kind == "DropdownMorph":
            return DropdownMorph(rx, ry, w, h, options=[lbl or "Option A", "Option B"])
        if kind == "ProgressBarMorph":
            return ProgressBarMorph(rx, ry, w, h, value=0.6)
        if kind == "ListMorph":
            return ListMorph(rx, ry, w, h, items=["Item 1", "Item 2", "Item 3"])
        if kind == "TableMorph":
            return TableMorph(rx, ry, w, h, columns=["Col A", "Col B"], rows=[["1", "Alpha"], ["2", "Beta"]])
        if kind == "TreeMorph":
            return TreeMorph(rx, ry, w, h, nodes=[{"label": "Root", "expanded": True, "children": [{"label": "Leaf", "children": []}]}])
        return CodeEditorMorph(rx, ry, w, h, text=lbl or "# code")

    def sync_item_morph(self, item: Dict[str, Any]) -> None:
        item["morph"] = self._build_preview_morph(item)

    def _sync_all_positions(self) -> None:
        for item in self.items:
            m = item.get("morph")
            if m is not None:
                m.x = self.x + item["x"]
                m.y = self.y + item["y"]
                m.width = item["width"]
                m.height = item["height"]

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        self._sync_all_positions()

    def _handle_rects(self, item: Dict[str, Any]) -> Dict[str, Tuple[float, float, float, float]]:
        hs = self.HANDLE_SIZE
        half = hs / 2.0
        ix = self.x + item["x"]
        iy = self.y + item["y"]
        iw = item["width"]
        ih = item["height"]
        return {
            "nw": (ix - half, iy - half, hs, hs),
            "ne": (ix + iw - half, iy - half, hs, hs),
            "sw": (ix - half, iy + ih - half, hs, hs),
            "se": (ix + iw - half, iy + ih - half, hs, hs),
        }

    def _hit_item(self, px: float, py: float) -> int:
        for idx in range(len(self.items) - 1, -1, -1):
            it = self.items[idx]
            ix = self.x + it["x"]
            iy = self.y + it["y"]
            if ix <= px <= ix + it["width"] and iy <= py <= iy + it["height"]:
                return idx
        return -1

    def _apply_smart_snap(self, idx: int, nx: float, ny: float, nw: float, nh: float) -> Tuple[float, float]:
        self.active_vguides = []
        self.active_hguides = []
        if not self.smart_guides:
            return (_snap_val(nx, self.GRID_SIZE, self.snap_grid), _snap_val(ny, self.GRID_SIZE, self.snap_grid))

        best_dx: Optional[float] = None
        best_vg: Optional[float] = None
        best_dy: Optional[float] = None
        best_hg: Optional[float] = None

        my_xs = [nx, nx + nw / 2.0, nx + nw]
        my_ys = [ny, ny + nh / 2.0, ny + nh]

        for j, sib in enumerate(self.items):
            if j == idx:
                continue
            sx, sy, sw, sh = sib["x"], sib["y"], sib["width"], sib["height"]
            sib_xs = [sx, sx + sw / 2.0, sx + sw]
            sib_ys = [sy, sy + sh / 2.0, sy + sh]
            for mx in my_xs:
                for tx in sib_xs:
                    diff = tx - mx
                    if abs(diff) <= self.SNAP_TOL and (best_dx is None or abs(diff) < abs(best_dx)):
                        best_dx = diff
                        best_vg = tx
            for my in my_ys:
                for ty in sib_ys:
                    diff = ty - my
                    if abs(diff) <= self.SNAP_TOL and (best_dy is None or abs(diff) < abs(best_dy)):
                        best_dy = diff
                        best_hg = ty

        if best_dx is not None:
            nx += best_dx
            if best_vg is not None:
                self.active_vguides.append(best_vg)
        else:
            nx = _snap_val(nx, self.GRID_SIZE, self.snap_grid)

        if best_dy is not None:
            ny += best_dy
            if best_hg is not None:
                self.active_hguides.append(best_hg)
        else:
            ny = _snap_val(ny, self.GRID_SIZE, self.snap_grid)

        return (nx, ny)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        if 0 <= self.selected_index < len(self.items):
            sel = self.items[self.selected_index]
            for corner, (hx, hy, hw, hh) in self._handle_rects(sel).items():
                if hx - 2 <= px <= hx + hw + 2 and hy - 2 <= py <= hy + hh + 2:
                    self._drag_mode = corner
                    self._drag_start_px = px
                    self._drag_start_py = py
                    self._orig_rect = (sel["x"], sel["y"], sel["width"], sel["height"])
                    return

        hit = self._hit_item(px, py)
        self.selected_index = hit
        self.builder.on_selection_changed()
        if hit >= 0:
            sel = self.items[hit]
            self._drag_mode = "move"
            self._drag_start_px = px
            self._drag_start_py = py
            self._orig_rect = (sel["x"], sel["y"], sel["width"], sel["height"])
        else:
            self._drag_mode = None
        self.changed()

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if self._drag_mode is None or not (0 <= self.selected_index < len(self.items)):
            return
        sel = self.items[self.selected_index]
        ox, oy, ow, oh = self._orig_rect
        mdx = px - self._drag_start_px
        mdy = py - self._drag_start_py

        if self._drag_mode == "move":
            nx = max(0.0, min(self.width - ow, ox + mdx))
            ny = max(0.0, min(self.height - oh, oy + mdy))
            nx, ny = self._apply_smart_snap(self.selected_index, nx, ny, ow, oh)
            sel["x"] = max(0.0, min(self.width - ow, nx))
            sel["y"] = max(0.0, min(self.height - oh, ny))
        else:
            nx, ny, nw, nh = ox, oy, ow, oh
            if "e" in self._drag_mode:
                nw = max(24.0, _snap_val(ow + mdx, self.GRID_SIZE, self.snap_grid))
            if "s" in self._drag_mode:
                nh = max(20.0, _snap_val(oh + mdy, self.GRID_SIZE, self.snap_grid))
            if "w" in self._drag_mode:
                new_x = _snap_val(ox + mdx, self.GRID_SIZE, self.snap_grid)
                if ox + ow - new_x >= 24.0:
                    nw = ox + ow - new_x
                    nx = max(0.0, new_x)
            if "n" in self._drag_mode:
                new_y = _snap_val(oy + mdy, self.GRID_SIZE, self.snap_grid)
                if oy + oh - new_y >= 20.0:
                    nh = oy + oh - new_y
                    ny = max(0.0, new_y)
            sel["x"], sel["y"], sel["width"], sel["height"] = nx, ny, nw, nh

        self.sync_item_morph(sel)
        self.changed()

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self._drag_mode = None
        self.active_vguides = []
        self.active_hguides = []
        self.changed()

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        canvas.push_clip(self.x + 1, self.y + 1, max(4.0, self.width - 2), max(4.0, self.height - 2))
        try:
            if self.snap_grid:
                gx = self.x + self.GRID_SIZE
                while gx < self.x + self.width:
                    gy = self.y + self.GRID_SIZE
                    while gy < self.y + self.height:
                        canvas.fill_rect(gx, gy, 1.5, 1.5, "#2a303c")
                        gy += self.GRID_SIZE
                    gx += self.GRID_SIZE

            self._sync_all_positions()
            for idx, item in enumerate(self.items):
                m = item.get("morph")
                if m is not None:
                    m.full_draw_on(canvas)
                if idx == self.selected_index:
                    ix = self.x + item["x"]
                    iy = self.y + item["y"]
                    canvas.stroke_rect(ix - 1, iy - 1, item["width"] + 2, item["height"] + 2, "#88c0d0", 1.5)
                    for hx, hy, hw, hh in self._handle_rects(item).values():
                        canvas.fill_rect(hx, hy, hw, hh, "#ebcb8b")
                        canvas.stroke_rect(hx, hy, hw, hh, "#1b1f27", 1.0)

            for vg in self.active_vguides:
                canvas.draw_line(self.x + vg, self.y, self.x + vg, self.y + self.height, "#88c0d0", 1.0)
            for hg in self.active_hguides:
                canvas.draw_line(self.x, self.y + hg, self.x + self.width, self.y + hg, "#88c0d0", 1.0)
        finally:
            canvas.pop_clip()


class AppBuilderWindow(SystemWindowMorph):
    """
    Visual Morphic App Builder:
    - Left palette: drag-and-drop or click widgets onto the design canvas
    - Center canvas: grid & smart-guide snapping + corner resize handles
    - Right panel: outlet names, labels, and Morphic two-way class/instance variable bindings
    - Top toolbar: Class Name, Snap toggle, Build Class, Spawn Live, Delete
    """

    def __init__(
        self,
        world: Optional[Any] = None,
        x: float = 50,
        y: float = 40,
        width: float = 920,
        height: float = 560,
    ):
        super().__init__(
            title="App Builder",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b536e",
        )
        self.world_ref = world
        self._palette_drag_kind: Optional[str] = None
        self._palette_drag_pos: Tuple[float, float] = (0.0, 0.0)
        self._updating_inspector: bool = False

        # Top toolbar
        self.class_name_input = TextInputMorph(
            x + 8, y + 32, 160, 26, text="MyCustomApp", placeholder="Class name"
        )
        self.snap_checkbox = CheckboxMorph(
            x + 178, y + 33, 92, 24, label="Snap 10px", checked=True,
            on_change=self._on_snap_toggle,
        )
        self.guides_checkbox = CheckboxMorph(
            x + 276, y + 33, 86, 24, label="Guides", checked=True,
            on_change=self._on_guides_toggle,
        )
        self.build_btn = ButtonMorph("Build Class", x + 372, y + 32, 92, 26, on_click=self.build_class, color="#3b536e")
        self.spawn_btn = ButtonMorph("Spawn Live", x + 470, y + 32, 92, 26, on_click=self.spawn_live_app, color="#4c6b53")
        self.delete_btn = ButtonMorph("Delete Widget", x + 568, y + 32, 102, 26, on_click=self.delete_selected, color="#6b3b42")

        # Main 3 panes
        self.palette = _DesignPaletteMorph(x + 8, y + 64, 152, height - 74, self)
        self.canvas_area = _DesignCanvasMorph(x + 166, y + 64, width - 404, height - 74, self)
        self.inspector_panel = Morph(x + width - 232, y + 64, 224, height - 74, color="#1b1f27", border_color="#4c566a", border_width=1.0)

        # Right inspector fields
        ix = self.inspector_panel.x + 10
        iy = self.inspector_panel.y + 10
        iw = 204.0
        self._lbl_header = LabelMorph("Properties & Bindings", ix, iy, color="#88c0d0", font="bold 11px sans-serif")
        self._lbl_outlet = LabelMorph("Outlet (self.<name>):", ix, iy + 26, color="#d8dee9", font="11px sans-serif")
        self.outlet_input = TextInputMorph(ix, iy + 44, iw, 24, placeholder="outlet_name", on_change=self._apply_inspector)

        self._lbl_label = LabelMorph("Label / Text:", ix, iy + 76, color="#d8dee9", font="11px sans-serif")
        self.label_input = TextInputMorph(ix, iy + 94, iw, 24, placeholder="Label...", on_change=self._apply_inspector)

        self._lbl_bind_t = LabelMorph("Bind Target:", ix, iy + 126, color="#d8dee9", font="11px sans-serif")
        self.bind_target_dd = DropdownMorph(
            ix, iy + 144, iw, 26, options=BIND_TARGETS, selected_index=0,
            on_change=lambda _i, _v: self._apply_inspector(""),
        )

        self._lbl_bind_v = LabelMorph("Bind Variable:", ix, iy + 178, color="#d8dee9", font="11px sans-serif")
        self.bind_var_input = TextInputMorph(ix, iy + 196, iw, 24, placeholder="e.g. username", on_change=self._apply_inspector)

        self._lbl_action = LabelMorph("Action Method:", ix, iy + 228, color="#d8dee9", font="11px sans-serif")
        self.action_input = TextInputMorph(ix, iy + 246, iw, 24, placeholder="e.g. on_submit", on_change=self._apply_inspector)

        self.status_lbl = LabelMorph("Drag/click widgets to design", ix, iy + 286, color="#a3be8c", font="11px sans-serif")

        for m in (
            self.class_name_input,
            self.snap_checkbox,
            self.guides_checkbox,
            self.build_btn,
            self.spawn_btn,
            self.delete_btn,
            self.palette,
            self.canvas_area,
            self.inspector_panel,
        ):
            self.add_morph(m)

        for m in (
            self._lbl_header,
            self._lbl_outlet,
            self.outlet_input,
            self._lbl_label,
            self.label_input,
            self._lbl_bind_t,
            self.bind_target_dd,
            self._lbl_bind_v,
            self.bind_var_input,
            self._lbl_action,
            self.action_input,
            self.status_lbl,
        ):
            self.inspector_panel.add_morph(m)

    def _on_snap_toggle(self, val: bool) -> None:
        self.canvas_area.snap_grid = bool(val)
        self.canvas_area.changed()

    def _on_guides_toggle(self, val: bool) -> None:
        self.canvas_area.smart_guides = bool(val)
        self.canvas_area.changed()

    def set_palette_drag(self, kind: str, px: float, py: float) -> None:
        self._palette_drag_kind = kind
        self._palette_drag_pos = (px, py)
        self.changed()

    def clear_palette_drag(self) -> None:
        self._palette_drag_kind = None
        self.changed()

    def drop_palette_widget(self, kind: str, px: float, py: float) -> Optional[Dict[str, Any]]:
        if self.canvas_area.contains_point(px, py):
            rel_x = max(0.0, px - self.canvas_area.x)
            rel_y = max(0.0, py - self.canvas_area.y)
            return self.add_widget_from_palette(kind, rel_x, rel_y)
        return None

    def add_widget_from_palette(
        self, kind: str, rel_x: Optional[float] = None, rel_y: Optional[float] = None
    ) -> Dict[str, Any]:
        spec = next((s for s in WIDGET_SPECS if s[0] == kind), (kind, 140.0, 28.0, ""))
        _, dw, dh, default_lbl = spec
        count = len(self.canvas_area.items) + 1
        base = kind.replace("Morph", "").lower()
        outlet = f"{base}_{count}"
        if rel_x is None:
            rel_x = 20.0 + ((count - 1) % 3) * 30.0
        if rel_y is None:
            rel_y = 20.0 + (count - 1) * 34.0
        nx = _snap_val(max(0.0, min(self.canvas_area.width - dw, rel_x)), self.canvas_area.GRID_SIZE, self.canvas_area.snap_grid)
        ny = _snap_val(max(0.0, min(self.canvas_area.height - dh, rel_y)), self.canvas_area.GRID_SIZE, self.canvas_area.snap_grid)

        item: Dict[str, Any] = {
            "kind": kind,
            "outlet": outlet,
            "x": nx,
            "y": ny,
            "width": dw,
            "height": dh,
            "label": default_lbl,
            "bind_target": BIND_TARGETS[0],
            "bind_var": "",
            "action": "",
        }
        self.canvas_area.sync_item_morph(item)
        self.canvas_area.items.append(item)
        self.canvas_area.selected_index = len(self.canvas_area.items) - 1
        self.on_selection_changed()
        self.changed()
        return item

    def selected_item(self) -> Optional[Dict[str, Any]]:
        idx = self.canvas_area.selected_index
        if 0 <= idx < len(self.canvas_area.items):
            return self.canvas_area.items[idx]
        return None

    def on_selection_changed(self) -> None:
        item = self.selected_item()
        self._updating_inspector = True
        try:
            if item is None:
                self.outlet_input.set_text("")
                self.label_input.set_text("")
                self.bind_target_dd.select_index(0, notify=False)
                self.bind_var_input.set_text("")
                self.action_input.set_text("")
            else:
                self.outlet_input.set_text(item.get("outlet", ""))
                self.label_input.set_text(item.get("label", ""))
                bt = item.get("bind_target", BIND_TARGETS[0])
                bidx = BIND_TARGETS.index(bt) if bt in BIND_TARGETS else 0
                self.bind_target_dd.select_index(bidx, notify=False)
                self.bind_var_input.set_text(item.get("bind_var", ""))
                self.action_input.set_text(item.get("action", ""))
        finally:
            self._updating_inspector = False

    def _apply_inspector(self, _val: str = "") -> None:
        if self._updating_inspector:
            return
        item = self.selected_item()
        if item is None:
            return
        item["outlet"] = _sanitize_ident(self.outlet_input.text, item["outlet"])
        item["label"] = self.label_input.text
        item["bind_target"] = self.bind_target_dd.selected_value
        item["bind_var"] = _sanitize_ident(self.bind_var_input.text, "") if self.bind_var_input.text.strip() else ""
        item["action"] = _sanitize_ident(self.action_input.text, "") if self.action_input.text.strip() else ""
        self.canvas_area.sync_item_morph(item)
        self.canvas_area.changed()

    def delete_selected(self) -> None:
        idx = self.canvas_area.selected_index
        if 0 <= idx < len(self.canvas_area.items):
            self.canvas_area.items.pop(idx)
            self.canvas_area.selected_index = min(idx, len(self.canvas_area.items) - 1)
            self.on_selection_changed()
            self.changed()

    def _default_value_for(self, kind: str, label: str) -> Any:
        if kind in ("CheckboxMorph", "ToggleSwitchMorph"):
            return True
        if kind == "SliderMorph":
            return 50.0
        if kind == "ProgressBarMorph":
            return 0.6
        return label

    def generate_class_source(self) -> str:
        cls_name = _sanitize_ident(self.class_name_input.text, "MyCustomApp")
        win_w = max(320, int(round(self.canvas_area.width + 20)))
        win_h = max(220, int(round(self.canvas_area.height + 42)))

        class_vars: Dict[str, Any] = {}
        inst_vars: Dict[str, Any] = {}
        actions: List[str] = []
        bindings: List[Tuple[str, str, str, str]] = []

        for idx, item in enumerate(self.canvas_area.items):
            kind = item["kind"]
            bvar = item.get("bind_var", "").strip()
            btgt = item.get("bind_target", BIND_TARGETS[0])
            act = item.get("action", "").strip()
            outlet = _sanitize_ident(item.get("outlet", ""), f"widget_{idx + 1}")
            if bvar:
                dval = self._default_value_for(kind, item.get("label", ""))
                if btgt == BIND_TARGETS[1]:
                    class_vars.setdefault(bvar, dval)
                elif btgt == BIND_TARGETS[0]:
                    inst_vars.setdefault(bvar, dval)
                bindings.append((outlet, kind, btgt, bvar))
            if act and act not in actions:
                actions.append(act)

        lines: List[str] = [f"class {cls_name}(SystemWindowMorph):"]
        lines.append(f'    """Generated by AppBuilderWindow."""')
        for k, v in class_vars.items():
            lines.append(f"    {k} = {repr(v)}")
        lines.append("")
        lines.append(f"    def __init__(self, world=None, x=100, y=80, width={win_w}, height={win_h}):")
        lines.append(f'        super().__init__(title="{cls_name}", x=x, y=y, width=width, height=height)')
        lines.append("        self.world_ref = world")
        lines.append("        self._binding_cache = {}")
        for k, v in inst_vars.items():
            lines.append(f"        self.{k} = {repr(v)}")
        lines.append("        bx = self.x + 10.0")
        lines.append("        by = self.y + self.TITLEBAR_HEIGHT + 6.0")

        for idx, item in enumerate(self.canvas_area.items):
            kind = item["kind"]
            outlet = _sanitize_ident(item.get("outlet", ""), f"widget_{idx + 1}")
            rx, ry, rw, rh = item["x"], item["y"], item["width"], item["height"]
            lbl = repr(item.get("label", ""))
            bvar = item.get("bind_var", "").strip()
            btgt = item.get("bind_target", BIND_TARGETS[0])
            act = item.get("action", "").strip()

            cb_parts: List[str] = []
            if bvar:
                if btgt == BIND_TARGETS[1]:
                    cb_parts.append(f"setattr(type(self), {repr(bvar)}, v)")
                elif btgt == BIND_TARGETS[2]:
                    cb_parts.append(f"self._set_global({repr(bvar)}, v)")
                else:
                    cb_parts.append(f"setattr(self, {repr(bvar)}, v)")
            if act:
                cb_parts.append(f"self.{act}()")
            cb_expr = f"lambda v=None: ({'; '.join(cb_parts)})" if cb_parts else "None"

            if kind == "LabelMorph":
                lines.append(f"        self.{outlet} = LabelMorph({lbl or repr('Label')}, bx + {rx}, by + {ry})")
                lines.append(f"        self.{outlet}.width, self.{outlet}.height = {rw}, {rh}")
            elif kind == "ButtonMorph":
                lines.append(f"        self.{outlet} = ButtonMorph({lbl or repr('Button')}, bx + {rx}, by + {ry}, {rw}, {rh}, on_click={cb_expr})")
            elif kind == "TextInputMorph":
                lines.append(f"        self.{outlet} = TextInputMorph(bx + {rx}, by + {ry}, {rw}, {rh}, text={lbl}, on_change={cb_expr})")
            elif kind == "CheckboxMorph":
                lines.append(f"        self.{outlet} = CheckboxMorph(bx + {rx}, by + {ry}, {rw}, {rh}, label={lbl or repr('Option')}, checked=True, on_change={cb_expr})")
            elif kind == "ToggleSwitchMorph":
                lines.append(f"        self.{outlet} = ToggleSwitchMorph(bx + {rx}, by + {ry}, {rw}, {rh}, label={lbl or repr('Toggle')}, checked=True, on_change={cb_expr})")
            elif kind == "SliderMorph":
                lines.append(f"        self.{outlet} = SliderMorph(bx + {rx}, by + {ry}, {rw}, {rh}, min_val=0, max_val=100, value=50, on_change={cb_expr})")
            elif kind == "DropdownMorph":
                opt_cb = f"lambda _i, v: ({'; '.join(cb_parts)})" if cb_parts else "None"
                lines.append(f"        self.{outlet} = DropdownMorph(bx + {rx}, by + {ry}, {rw}, {rh}, options=[{lbl or repr('Option A')}, 'Option B'], on_change={opt_cb})")
            elif kind == "ProgressBarMorph":
                lines.append(f"        self.{outlet} = ProgressBarMorph(bx + {rx}, by + {ry}, {rw}, {rh}, value=0.6)")
            elif kind == "ListMorph":
                lines.append(f"        self.{outlet} = ListMorph(bx + {rx}, by + {ry}, {rw}, {rh}, items=['Item 1', 'Item 2'])")
            elif kind == "TableMorph":
                lines.append(f"        self.{outlet} = TableMorph(bx + {rx}, by + {ry}, {rw}, {rh}, columns=['Col A', 'Col B'], rows=[['1', 'Alpha']])")
            elif kind == "TreeMorph":
                lines.append(f"        self.{outlet} = TreeMorph(bx + {rx}, by + {ry}, {rw}, {rh}, nodes=[{{'label': 'Root', 'expanded': True, 'children': []}}])")
            else:
                lines.append(f"        self.{outlet} = CodeEditorMorph(bx + {rx}, by + {ry}, {rw}, {rh}, text={lbl or repr('# code')})")
            lines.append(f"        self.add_morph(self.{outlet})")

        lines.append("")
        lines.append("    def _get_global(self, name, default=None):")
        lines.append("        w = self.world() or self.world_ref")
        lines.append("        if w is not None and name in getattr(w, 'workspace_globals', {}):")
        lines.append("            return w.workspace_globals[name]")
        lines.append("        return default")
        lines.append("")
        lines.append("    def _set_global(self, name, value):")
        lines.append("        w = self.world() or self.world_ref")
        lines.append("        if w is not None and hasattr(w, 'workspace_globals'):")
        lines.append("            w.workspace_globals[name] = value")
        lines.append("")
        lines.append("    def wants_steps(self):")
        lines.append("        return True")
        lines.append("")
        lines.append("    def step(self):")
        lines.append("        self.sync_bindings()")
        lines.append("")
        lines.append("    def sync_bindings(self):")
        if not bindings:
            lines.append("        return")
        else:
            for outlet, kind, btgt, bvar in bindings:
                if btgt == BIND_TARGETS[1]:
                    lines.append(f"        val = getattr(type(self), {repr(bvar)}, None)")
                elif btgt == BIND_TARGETS[2]:
                    lines.append(f"        val = self._get_global({repr(bvar)})")
                else:
                    lines.append(f"        val = getattr(self, {repr(bvar)}, None)")
                lines.append(f"        if val != self._binding_cache.get({repr(outlet)}):")
                lines.append(f"            self._binding_cache[{repr(outlet)}] = val")
                if kind == "LabelMorph":
                    lines.append(f"            self.{outlet}.text = str(val)")
                    lines.append(f"            self.{outlet}.changed()")
                elif kind == "TextInputMorph":
                    lines.append(f"            if self.{outlet}.text != str(val):")
                    lines.append(f"                self.{outlet}.set_text(str(val), notify=False)")
                elif kind in ("CheckboxMorph", "ToggleSwitchMorph"):
                    lines.append(f"            self.{outlet}.checked = bool(val)")
                    lines.append(f"            self.{outlet}.changed()")
                elif kind == "SliderMorph":
                    lines.append(f"            self.{outlet}.set_value(float(val), notify=False)")
                elif kind == "ProgressBarMorph":
                    lines.append(f"            self.{outlet}.set_value(float(val))")

        for act in actions:
            lines.append("")
            lines.append(f"    def {act}(self):")
            lines.append("        pass")

        return "\n".join(lines) + "\n"

    def build_class(self) -> Optional[Any]:
        w = self.world() or self.world_ref
        if w is None or getattr(w, "smalltalk", None) is None:
            self.status_lbl.text = "No Smalltalk kernel"
            self.status_lbl.changed()
            return None
        src = self.generate_class_source()
        try:
            cls_obj = w.smalltalk.define_class("User-Objects", src)
            self.status_lbl.text = f"Built {cls_obj.__name__}"
            self.status_lbl.changed()
            return cls_obj
        except Exception as exc:
            self.status_lbl.text = f"Error: {exc}"
            self.status_lbl.changed()
            return None

    def spawn_live_app(self) -> Optional[Morph]:
        cls_obj = self.build_class()
        w = self.world() or self.world_ref
        if cls_obj is None or w is None:
            return None
        inst = cls_obj(w)
        w.add_morph(inst)
        inst.bring_to_front()
        self.status_lbl.text = f"Spawned {cls_obj.__name__}"
        self.status_lbl.changed()
        return inst

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        if not hasattr(self, "palette"):
            return
        dx_p = (self.x + 8.0) - self.palette.x
        dy_p = (self.y + 64.0) - self.palette.y
        if dx_p or dy_p:
            self.palette.move_by(dx_p, dy_p)
        self.palette.set_extent(152.0, max(120.0, self.height - 74.0))

        dx_c = (self.x + 166.0) - self.canvas_area.x
        dy_c = (self.y + 64.0) - self.canvas_area.y
        if dx_c or dy_c:
            self.canvas_area.move_by(dx_c, dy_c)
        self.canvas_area.set_extent(max(180.0, self.width - 404.0), max(120.0, self.height - 74.0))

        dx_i = (self.x + self.width - 232.0) - self.inspector_panel.x
        dy_i = (self.y + 64.0) - self.inspector_panel.y
        if dx_i or dy_i:
            self.inspector_panel.move_by(dx_i, dy_i)
        self.inspector_panel.set_extent(224.0, max(120.0, self.height - 74.0))

    def full_draw_on(self, canvas: DisplayCanvas) -> None:
        super().full_draw_on(canvas)
        if self._palette_drag_kind is not None:
            gx, gy = self._palette_drag_pos
            canvas.fill_round_rect(gx - 40, gy - 12, 110, 24, 4.0, "rgba(136,192,208,0.28)", "#88c0d0", 1.2)
            canvas.draw_text(self._palette_drag_kind.replace("Morph", ""), gx - 32, gy + 4, color="#eceff4", font="11px monospace")
