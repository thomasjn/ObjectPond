from typing import Any, Dict, List, Optional
from objectpond.morphic.canvas import DisplayCanvas, Form
from objectpond.morphic.sound import ADSR, SampledSound, SoundSynth
from objectpond.morphic.morph import Morph
from objectpond.morphic.widgets import ButtonMorph, LabelMorph, SystemWindowMorph
from objectpond.morphic.app_widgets import (
    CheckboxMorph,
    DialogMorph,
    DropdownMorph,
    ImageMorph,
    ProgressBarMorph,
    SliderMorph,
    TableMorph,
    TextInputMorph,
    ToggleSwitchMorph,
    TreeMorph,
)
from objectpond.morphic.containers import (
    ColumnMorph,
    RowMorph,
    ScrollPaneMorph,
    SplitPaneMorph,
    TabViewMorph,
)


class BouncingAtomsMorph(Morph):
    """
    Live animated simulation Morph.
    Spawns multiple colorful atoms bouncing inside its boundaries, stepping on every World cycle.
    Supports live method hot-patching (e.g. patching `step` via the System Browser).
    """

    def __init__(
        self,
        x: float = 100,
        y: float = 100,
        width: float = 280,
        height: float = 200,
        num_atoms: int = 14,
    ):
        super().__init__(
            x=x,
            y=y,
            width=width,
            height=height,
            color="#1b1f27",
            border_color="#5e81ac",
            border_width=1.5,
        )
        self.corner_radius = 6.0
        colors = [
            "#e06c75",
            "#98c379",
            "#e5c07b",
            "#61afef",
            "#c678dd",
            "#56b6c2",
            "#ff9f1c",
            "#2ec4b6",
        ]
        self.atoms: List[Dict[str, Any]] = []
        for i in range(num_atoms):
            vx = ((i % 5) - 2.0) * 1.4
            if abs(vx) < 0.5:
                vx = 2.0
            vy = (((i * 2) % 5) - 2.0) * 1.3
            if abs(vy) < 0.5:
                vy = -2.0
            self.atoms.append(
                {
                    "x": self.x + 20.0 + (i * 18.0) % max(20.0, self.width - 40.0),
                    "y": self.y + 20.0 + (i * 14.0) % max(20.0, self.height - 40.0),
                    "vx": vx,
                    "vy": vy,
                    "radius": 5.5,
                    "color": colors[i % len(colors)],
                }
            )

    def wants_steps(self) -> bool:
        return True

    def step(self) -> None:
        min_x = self.x + 8.0
        max_x = self.x + self.width - 8.0
        min_y = self.y + 8.0
        max_y = self.y + self.height - 8.0

        for atom in self.atoms:
            atom["x"] += atom["vx"]
            atom["y"] += atom["vy"]
            r = atom.get("radius", 5.5)
            if atom["x"] - r < min_x:
                atom["x"] = min_x + r
                atom["vx"] = abs(atom["vx"])
            elif atom["x"] + r > max_x:
                atom["x"] = max_x - r
                atom["vx"] = -abs(atom["vx"])

            if atom["y"] - r < min_y:
                atom["y"] = min_y + r
                atom["vy"] = abs(atom["vy"])
            elif atom["y"] + r > max_y:
                atom["y"] = max_y - r
                atom["vy"] = -abs(atom["vy"])

        self.changed()

    def move_by(self, dx: float, dy: float) -> None:
        super().move_by(dx, dy)
        for atom in getattr(self, "atoms", []):
            atom["x"] += dx
            atom["y"] += dy

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
        canvas.draw_text(
            f"Bouncing Atoms ({len(self.atoms)})",
            self.x + 8,
            self.y + 16,
            color="#4c566a",
            font="11px monospace",
        )
        for atom in self.atoms:
            canvas.fill_circle(
                atom["x"],
                atom["y"],
                atom.get("radius", 5.5),
                atom["color"],
                stroke_color="#181a20",
                line_width=1.0,
            )


class BitBltPaintMorph(Morph):
    """
    Interactive pixel painting Morph backed by a 32-bit Form bitmap.
    Demonstrates BitBlt raster graphics operations, color palette swatches,
    and direct pixel buffer blitting.
    """

    def __init__(
        self,
        x: float = 200,
        y: float = 200,
        width: float = 240,
        height: float = 180,
    ):
        super().__init__(
            x=x,
            y=y,
            width=width,
            height=height,
            color="#252b37",
            border_color="#5e81ac",
            border_width=1.5,
        )
        self.corner_radius = 4.0
        bw = max(10, int(width - 4))
        bh = max(10, int(height - 28))
        self.bitmap = Form(bw, bh, fill_color=0xFF1E222A)

        self.palette = [
            ("#bf616a", 0xFFBF616A),  # Red
            ("#d08770", 0xFFD08770),  # Orange
            ("#ebcb8b", 0xFFEBCB8B),  # Yellow
            ("#a3be8c", 0xFFA3BE8C),  # Green
            ("#88c0d0", 0xFF88C0D0),  # Cyan
            ("#5e81ac", 0xFF5E81AC),  # Blue
            ("#b48ead", 0xFFB48EAD),  # Purple
            ("#eceff4", 0xFFECEFF4),  # White
            ("#1e222a", 0xFF1E222A),  # Eraser
        ]
        self.current_color32: int = 0xFF88C0D0
        self.brush_size: int = 4
        self.is_painting: bool = False
        self._last_px: float = 0.0
        self._last_py: float = 0.0

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "bitmap") or self.bitmap is None:
            return
        bw = max(10, int(self.width - 4))
        bh = max(10, int(self.height - 28))
        if bw != self.bitmap.width or bh != self.bitmap.height:
            new_bmp = Form(bw, bh, fill_color=0xFF1E222A)
            new_bmp.copy_bits(
                self.bitmap,
                0,
                0,
                min(bw, self.bitmap.width),
                min(bh, self.bitmap.height),
                0,
                0,
            )
            self.bitmap = new_bmp

    def paint_stroke(self, px: float, py: float) -> None:
        bx = int(px - (self.x + 2))
        by = int(py - (self.y + 26))
        bs = self.brush_size
        self.bitmap.fill_rect(bx - bs // 2, by - bs // 2, bs, bs, self.current_color32)
        self.changed()

    def paint_line(self, x0: float, y0: float, x1: float, y1: float) -> None:
        steps = int(max(abs(x1 - x0), abs(y1 - y0), 1.0))
        for i in range(steps + 1):
            t = i / steps
            self.paint_stroke(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        self.bring_to_front()
        if py <= self.y + 24:
            sw_x = self.x + 6
            for _hex_col, col32 in self.palette:
                if sw_x <= px <= sw_x + 18 and self.y + 4 <= py <= self.y + 22:
                    self.current_color32 = col32
                    self.is_painting = False
                    self.changed()
                    return
                sw_x += 22
            # Clicking in the top bar outside swatches allows dragging the morph
            self.is_painting = False
            return

        self.is_painting = True
        self._last_px = px
        self._last_py = py
        self.paint_stroke(px, py)

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        if self.is_painting:
            last_x = getattr(self, "_last_px", px)
            last_y = getattr(self, "_last_py", py)
            self.paint_line(last_x, last_y, px, py)
            self._last_px = px
            self._last_py = py

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        self.is_painting = False

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

        # Color palette swatches
        sw_x = self.x + 6
        for hex_col, col32 in self.palette:
            is_active = col32 == self.current_color32
            stroke = "#ffffff" if is_active else "#3b4252"
            canvas.fill_round_rect(
                sw_x,
                self.y + 4,
                18,
                16,
                2,
                hex_col,
                stroke,
                1.5 if is_active else 1.0,
            )
            sw_x += 22

        # Blit Form pixel buffer
        canvas.blit_form(self.bitmap, self.x + 2, self.y + 26)
        canvas.stroke_rect(
            self.x + 2,
            self.y + 26,
            self.bitmap.width,
            self.bitmap.height,
            "#434c5e",
            1.0,
        )


class WidgetShowcaseWindow(SystemWindowMorph):
    """Interactive showcase window demonstrating all app-style Morphic widgets and containers."""

    def __init__(
        self,
        world: Optional[Any] = None,
        x: float = 120,
        y: float = 60,
        width: float = 620,
        height: float = 430,
    ):
        super().__init__(
            title="Widget Showcase",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b526b",
        )
        self.world_ref = world
        cx, cy, cw, ch = self._content_bounds()

        # Shared state widgets
        self.status_label = LabelMorph("Interact with any widget below", 0, 0, color="#a3be8c")
        self.progress = ProgressBarMorph(0, 0, 220, 22, value=0.45)

        # Build a dynamic Form swatch for ImageMorph
        self.swatch_form = self._make_swatch_form(0xFF88C0D0)
        self.image_view = ImageMorph(0, 0, 64, 44, form=self.swatch_form)

        # Tab 1: Controls inside ScrollPaneMorph -> ColumnMorph -> RowMorphs
        controls_col = ColumnMorph(0, 0, cw - 24, 390, padding=12, spacing=12, color="#20252f")

        self.name_input = TextInputMorph(
            0, 0, 240, 28,
            text="ObjectPond",
            placeholder="Type a greeting...",
            on_change=lambda txt: self._set_status(f"Text: {txt}"),
            on_submit=lambda txt: self._set_status(f"Submitted: {txt}"),
        )
        row_input = RowMorph(0, 0, 480, 32, padding=0, spacing=10, align="center")
        row_input.add_child(LabelMorph("TextInput:", 0, 0, color="#d8dee9"))
        row_input.add_child(self.name_input, flex=1)

        self.checkbox = CheckboxMorph(
            0, 0, 170, 26,
            label="Indeterminate",
            checked=False,
            on_change=lambda v: self._toggle_indeterminate(v),
        )
        self.toggle = ToggleSwitchMorph(
            0, 0, 170, 26,
            label="Show % Label",
            checked=True,
            on_change=lambda v: self._toggle_progress_label(v),
        )
        row_bools = RowMorph(0, 0, 480, 30, padding=0, spacing=16, align="center")
        row_bools.add_child(self.checkbox)
        row_bools.add_child(self.toggle)

        self.slider = SliderMorph(
            0, 0, 220, 26,
            min_val=0, max_val=100, value=45, step=1,
            on_change=lambda v: self._on_slider(v),
        )
        row_slider = RowMorph(0, 0, 480, 30, padding=0, spacing=10, align="center")
        row_slider.add_child(LabelMorph("Slider:", 0, 0, color="#d8dee9"))
        row_slider.add_child(self.slider, flex=1)
        row_slider.add_child(self.progress)

        self.dropdown = DropdownMorph(
            0, 0, 160, 28,
            options=["Frost Cyan", "Aurora Green", "Amber Gold", "Crimson Red"],
            selected_index=0,
            on_change=lambda idx, val: self._on_theme_pick(idx, val),
        )
        self.dialog_btn = ButtonMorph(
            "Open Dialog...",
            width=130,
            height=28,
            on_click=self._open_demo_dialog,
            color="#5e81ac",
        )
        row_misc = RowMorph(0, 0, 480, 48, padding=0, spacing=12, align="center")
        row_misc.add_child(self.dropdown)
        row_misc.add_child(self.image_view)
        row_misc.add_child(self.dialog_btn)

        controls_col.add_child(self.status_label)
        controls_col.add_child(row_input)
        controls_col.add_child(row_bools)
        controls_col.add_child(row_slider)
        controls_col.add_child(row_misc)

        self.scroll_pane = ScrollPaneMorph(0, 0, cw, ch - 30, content=controls_col)

        # Tab 2: Data & Views (SplitPaneMorph -> TreeMorph + TableMorph)
        self._all_rows = [
            ["TextInputMorph", "Controls", "Single-line text"],
            ["CheckboxMorph", "Controls", "Boolean check"],
            ["ToggleSwitchMorph", "Controls", "On/off switch"],
            ["SliderMorph", "Controls", "Numeric range"],
            ["DropdownMorph", "Controls", "Menu selector"],
            ["ProgressBarMorph", "Feedback", "0..100% / pulse"],
            ["ImageMorph", "Display", "Form bitmap"],
            ["DialogMorph", "Feedback", "Modal prompt"],
            ["RowMorph / ColumnMorph", "Containers", "Flex layout"],
            ["ScrollPaneMorph", "Containers", "Clipped scroll"],
            ["TabViewMorph", "Containers", "Tabbed pages"],
            ["SplitPaneMorph", "Containers", "Draggable split"],
            ["TableMorph", "Data", "Sortable grid"],
            ["TreeMorph", "Data", "Expandable tree"],
        ]
        tree_nodes = [
            {
                "label": "All Widgets",
                "expanded": True,
                "data": None,
                "children": [
                    {"label": "Controls", "expanded": False, "data": "Controls", "children": []},
                    {"label": "Containers", "expanded": False, "data": "Containers", "children": []},
                    {"label": "Data", "expanded": False, "data": "Data", "children": []},
                    {"label": "Feedback", "expanded": False, "data": "Feedback", "children": []},
                    {"label": "Display", "expanded": False, "data": "Display", "children": []},
                ],
            }
        ]
        self.tree = TreeMorph(0, 0, 170, 260, nodes=tree_nodes, on_select=self._on_tree_select)
        self.table = TableMorph(
            0, 0, 360, 260,
            columns=["Widget", "Category", "Role"],
            rows=self._all_rows,
            on_select=lambda idx, row: self._set_status(f"Selected: {row[0]}"),
        )
        self.split_pane = SplitPaneMorph(0, 0, cw, ch - 30, first=self.tree, second=self.table, ratio=0.33)

        self.tabs = TabViewMorph(
            cx, cy, cw, ch,
            tabs=[("Controls & Layout", self.scroll_pane), ("Data & Views", self.split_pane)],
        )
        self.add_morph(self.tabs)

    def _set_status(self, msg: str) -> None:
        self.status_label.text = str(msg)
        self.status_label.changed()

    def _make_swatch_form(self, col32: int) -> Form:
        f = Form(56, 36, col32)
        f.fill_rect(4, 4, 48, 28, 0xFF1B1F27)
        f.fill_rect(8, 8, 40, 20, col32)
        return f

    def _toggle_indeterminate(self, v: bool) -> None:
        self.progress.indeterminate = bool(v)
        self._set_status(f"Indeterminate: {v}")
        self.progress.changed()

    def _toggle_progress_label(self, v: bool) -> None:
        self.progress.show_label = bool(v)
        self.progress.changed()

    def _on_slider(self, v: float) -> None:
        self.progress.set_value(v / 100.0)
        self._set_status(f"Slider: {int(round(v))}%")

    def _on_theme_pick(self, idx: int, val: str) -> None:
        palette = [("#88c0d0", 0xFF88C0D0), ("#a3be8c", 0xFFA3BE8C), ("#ebcb8b", 0xFFEBCB8B), ("#bf616a", 0xFFBF616A)]
        hex_c, c32 = palette[idx % len(palette)]
        self.progress.bar_color = hex_c
        self.image_view.set_form(self._make_swatch_form(c32))
        self._set_status(f"Accent: {val}")

    def _on_tree_select(self, node: Dict[str, Any]) -> None:
        cat = node.get("data")
        if cat is None:
            self.table.set_rows(self._all_rows)
        else:
            self.table.set_rows([r for r in self._all_rows if r[1] == cat])

    def _open_demo_dialog(self) -> None:
        w = self.world() or self.world_ref
        if w is None or not hasattr(w, "open_modal"):
            return
        dlg = DialogMorph(
            title="Update Greeting",
            message="Enter a new greeting for TextInput:",
            input_default=self.name_input.text,
            buttons=[
                ("Apply", lambda val: (self.name_input.set_text(val, notify=True), self._set_status(f"Applied: {val}"))),
                ("Cancel", None),
            ],
        )
        w.open_modal(dlg)

    def _content_bounds(self):
        return (
            self.x + 8.0,
            self.y + self.TITLEBAR_HEIGHT + 6.0,
            max(80.0, self.width - 16.0),
            max(80.0, self.height - self.TITLEBAR_HEIGHT - 14.0),
        )

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(w, h)
        if hasattr(self, "tabs"):
            cx, cy, cw, ch = self._content_bounds()
            dx, dy = cx - self.tabs.x, cy - self.tabs.y
            if dx != 0.0 or dy != 0.0:
                self.tabs.move_by(dx, dy)
            self.tabs.set_extent(cw, ch)


class _WaveformPreviewMorph(Morph):
    """Oscilloscope preview drawing a SampledSound's PCM waveform."""

    def __init__(self, x: float, y: float, width: float, height: float, sound: Optional[SampledSound] = None):
        super().__init__(x, y, width, height, color="#14171d", border_color="#4c566a", border_width=1.0)
        self.sound = sound

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
        canvas.stroke_rect(self.x, self.y, self.width, self.height, self.border_color, 1.0)
        mid_y = self.y + self.height / 2.0
        canvas.draw_line(self.x + 2, mid_y, self.x + self.width - 2, mid_y, "#2e3440", 1.0)
        if self.sound is None or not self.sound.samples:
            return
        samples = self.sound.samples
        n = len(samples)
        steps = max(10, int(self.width - 6))
        amp_h = max(4.0, (self.height - 10.0) / 2.0)
        prev_x = self.x + 3.0
        prev_y = mid_y - (samples[0] / 32768.0) * amp_h
        for i in range(1, steps):
            idx = min(n - 1, int(i * (n / float(steps))))
            px = self.x + 3.0 + i
            py = mid_y - (samples[idx] / 32768.0) * amp_h
            canvas.draw_line(prev_x, prev_y, px, py, "#88c0d0", 1.2)
            prev_x, prev_y = px, py


class SoundStudioWindow(SystemWindowMorph):
    """Interactive sound synthesizer with waveform oscilloscope, ADSR controls, playback, and global save."""

    def __init__(
        self,
        world: Optional[Any] = None,
        x: float = 140,
        y: float = 70,
        width: float = 480,
        height: float = 340,
    ):
        super().__init__(title="Sound Studio", x=x, y=y, width=width, height=height, header_color="#3b536e")
        self.world_ref = world
        self.current_sound: Optional[SampledSound] = None

        self.wave_dd = DropdownMorph(
            x + 12, y + 34, 150, 26,
            options=["sine", "square", "saw", "triangle", "fm_bell", "additive"],
            selected_index=0,
            on_change=lambda _i, _v: self.synthesize(),
        )
        self.play_btn = ButtonMorph("Play", x + 172, y + 34, 72, 26, on_click=self.play_current, color="#4c6b53")
        self.global_input = TextInputMorph(x + 254, y + 34, 120, 26, text="my_sound", placeholder="global name")
        self.save_btn = ButtonMorph("Save Global", x + 382, y + 34, 86, 26, on_click=self.save_to_global, color="#5e81ac")

        self.freq_slider = SliderMorph(x + 12, y + 70, 220, 24, min_val=110, max_val=880, value=440, step=1, on_change=lambda _v: self.synthesize())
        self.dur_slider = SliderMorph(x + 244, y + 70, 220, 24, min_val=0.1, max_val=2.0, value=0.5, step=0.05, on_change=lambda _v: self.synthesize())

        self.preview = _WaveformPreviewMorph(x + 12, y + 104, width - 24, height - 142)
        self.status_lbl = LabelMorph("Ready", x + 12, y + height - 28, color="#a3be8c")

        for m in (self.wave_dd, self.play_btn, self.global_input, self.save_btn, self.freq_slider, self.dur_slider, self.preview, self.status_lbl):
            self.add_morph(m)
        self.synthesize()

    def synthesize(self) -> SampledSound:
        wtype = self.wave_dd.selected_value
        freq = float(self.freq_slider.value)
        dur = float(self.dur_slider.value)
        env = ADSR(0.01, 0.1, 0.65, 0.15)
        if wtype == "fm_bell":
            snd = SoundSynth.fm(freq, freq * 1.4, 4.0, dur, env=env)
        elif wtype == "additive":
            snd = SoundSynth.additive(((1.0, 1.0), (2.0, 0.5), (3.0, 0.25), (4.0, 0.15)), freq, dur, env=env)
        else:
            snd = SoundSynth.oscillator(wtype, freq, dur, env=env)
        self.current_sound = snd
        self.preview.sound = snd
        self.preview.changed()
        self.status_lbl.text = f"{wtype} @ {int(round(freq))}Hz ({dur:.2f}s, {len(snd.samples)*2} bytes)"
        self.status_lbl.changed()
        return snd

    def play_current(self) -> bool:
        if self.current_sound is None:
            self.synthesize()
        w = self.world() or self.world_ref
        if w is not None and hasattr(w, "play_sound"):
            return w.play_sound(self.current_sound)
        return False

    def save_to_global(self) -> None:
        if self.current_sound is None:
            self.synthesize()
        name = self.global_input.text.strip() or "my_sound"
        w = self.world() or self.world_ref
        if w is not None and hasattr(w, "workspace_globals"):
            w.workspace_globals[name] = self.current_sound
            self.status_lbl.text = f"Saved '{name}' to Workspace globals"
            self.status_lbl.changed()



