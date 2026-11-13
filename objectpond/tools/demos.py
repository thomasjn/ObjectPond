from typing import Any, Dict, List
from objectpond.morphic.canvas import DisplayCanvas, Form
from objectpond.morphic.morph import Morph


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
