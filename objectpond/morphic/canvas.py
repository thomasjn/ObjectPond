import array
from typing import Any, List, Optional, Tuple


class Form:
    """
    Classic Smalltalk Form (32-bit RGBA bitmap) supporting low-level BitBlt operations.
    Each pixel is stored as a 32-bit unsigned integer (0xAABBGGRR or 0xAARRGGBB).
    """

    def __init__(self, width: int, height: int, fill_color: int = 0x00000000):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.pixels = array.array("I", [fill_color & 0xFFFFFFFF] * (self.width * self.height))

    def pixel_at(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.pixels[y * self.width + x]
        return 0

    def put_pixel(self, x: int, y: int, color32: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y * self.width + x] = color32 & 0xFFFFFFFF

    def fill_rect(self, x: int, y: int, w: int, h: int, color32: int) -> None:
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, int(x + w))
        y1 = min(self.height, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        c = color32 & 0xFFFFFFFF
        span = x1 - x0
        row_slice = array.array("I", [c] * span)
        for row in range(y0, y1):
            start = row * self.width + x0
            self.pixels[start : start + span] = row_slice

    def copy_bits(
        self,
        source_form: "Form",
        src_x: int,
        src_y: int,
        w: int,
        h: int,
        dst_x: int,
        dst_y: int,
    ) -> None:
        """BitBlt copyBits operation from `source_form` onto `self` with clipping."""
        for row in range(int(h)):
            sy = int(src_y) + row
            dy = int(dst_y) + row
            if not (0 <= sy < source_form.height and 0 <= dy < self.height):
                continue
            for col in range(int(w)):
                sx = int(src_x) + col
                dx = int(dst_x) + col
                if 0 <= sx < source_form.width and 0 <= dx < self.width:
                    c = source_form.pixels[sy * source_form.width + sx]
                    # Skip fully transparent pixels if alpha == 0
                    if (c >> 24) != 0:
                        self.pixels[dy * self.width + dx] = c

    def to_bytes(self) -> bytes:
        return self.pixels.tobytes()

    @classmethod
    def from_bytes(cls, width: int, height: int, raw: bytes) -> "Form":
        form = cls(width, height)
        arr = array.array("I")
        arr.frombytes(raw)
        expected = width * height
        if len(arr) >= expected:
            form.pixels = arr[:expected]
        return form


class RecordingBackend:
    """Headless canvas backend used for unit testing and command verification."""

    def __init__(self, width: int = 1024, height: int = 768):
        self.width = width
        self.height = height
        self.commands: List[Tuple[Any, ...]] = []

    def clear(self) -> None:
        self.commands.clear()

    def save_clip(self, x: float, y: float, w: float, h: float) -> None:
        self.commands.append(("save_clip", x, y, w, h))

    def restore_clip(self) -> None:
        self.commands.append(("restore_clip",))

    def fill_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        self.commands.append(("fill_rect", x, y, w, h, color))

    def stroke_rect(self, x: float, y: float, w: float, h: float, color: str, line_width: float = 1.0) -> None:
        self.commands.append(("stroke_rect", x, y, w, h, color, line_width))

    def fill_round_rect(self, x: float, y: float, w: float, h: float, radius: float, fill_color: str, stroke_color: Optional[str] = None, line_width: float = 1.0) -> None:
        self.commands.append(("fill_round_rect", x, y, w, h, radius, fill_color, stroke_color, line_width))

    def fill_circle(self, cx: float, cy: float, radius: float, fill_color: str, stroke_color: Optional[str] = None, line_width: float = 1.0) -> None:
        self.commands.append(("fill_circle", cx, cy, radius, fill_color, stroke_color, line_width))

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, color: str, line_width: float = 1.0) -> None:
        self.commands.append(("draw_line", x1, y1, x2, y2, color, line_width))

    def draw_text(self, text: str, x: float, y: float, color: str = "#ffffff", font: str = "13px monospace") -> None:
        self.commands.append(("draw_text", text, x, y, color, font))

    def measure_text(self, text: str, font: str = "13px monospace") -> float:
        return len(text) * 7.8

    def blit_form(self, form: Form, x: float, y: float) -> None:
        self.commands.append(("blit_form", form.width, form.height, x, y))


class JSCanvasBackend:
    """Browser HTML5 Canvas + BitBlt bridge backend used inside Pyodide WASM."""

    def __init__(self, js_bridge: Any):
        self.js_bridge = js_bridge

    def save_clip(self, x: float, y: float, w: float, h: float) -> None:
        self.js_bridge.saveClip(x, y, w, h)

    def restore_clip(self) -> None:
        self.js_bridge.restoreClip()

    def fill_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        self.js_bridge.fillRect(x, y, w, h, color)

    def stroke_rect(self, x: float, y: float, w: float, h: float, color: str, line_width: float = 1.0) -> None:
        self.js_bridge.strokeRect(x, y, w, h, color, line_width)

    def fill_round_rect(self, x: float, y: float, w: float, h: float, radius: float, fill_color: str, stroke_color: Optional[str] = None, line_width: float = 1.0) -> None:
        self.js_bridge.fillRoundRect(x, y, w, h, radius, fill_color, stroke_color or "", line_width)

    def fill_circle(self, cx: float, cy: float, radius: float, fill_color: str, stroke_color: Optional[str] = None, line_width: float = 1.0) -> None:
        self.js_bridge.fillCircle(cx, cy, radius, fill_color, stroke_color or "", line_width)

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, color: str, line_width: float = 1.0) -> None:
        self.js_bridge.drawLine(x1, y1, x2, y2, color, line_width)

    def draw_text(self, text: str, x: float, y: float, color: str = "#ffffff", font: str = "13px monospace") -> None:
        self.js_bridge.drawText(str(text), x, y, color, font)

    def measure_text(self, text: str, font: str = "13px monospace") -> float:
        try:
            return float(self.js_bridge.measureText(str(text), font))
        except Exception:
            return len(str(text)) * 7.8

    def blit_form(self, form: Form, x: float, y: float) -> None:
        self.js_bridge.blitForm(form.to_bytes(), form.width, form.height, int(x), int(y))


class DisplayCanvas:
    """
    Morphic Canvas providing clipping rectangles, drawing primitives,
    bevel borders, and Form BitBlt blitting.
    """

    def __init__(self, backend: Any):
        self.backend = backend
        self.clip_stack: List[Tuple[float, float, float, float]] = []

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        self.clip_stack.append((x, y, w, h))
        self.backend.save_clip(x, y, w, h)

    def pop_clip(self) -> None:
        if self.clip_stack:
            self.clip_stack.pop()
            self.backend.restore_clip()

    def fill_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        self.backend.fill_rect(x, y, w, h, color)

    def stroke_rect(self, x: float, y: float, w: float, h: float, color: str, line_width: float = 1.0) -> None:
        self.backend.stroke_rect(x, y, w, h, color, line_width)

    def fill_round_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        fill_color: str,
        stroke_color: Optional[str] = None,
        line_width: float = 1.0,
    ) -> None:
        self.backend.fill_round_rect(x, y, w, h, radius, fill_color, stroke_color, line_width)

    def fill_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        fill_color: str,
        stroke_color: Optional[str] = None,
        line_width: float = 1.0,
    ) -> None:
        self.backend.fill_circle(cx, cy, radius, fill_color, stroke_color, line_width)

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, color: str, line_width: float = 1.0) -> None:
        self.backend.draw_line(x1, y1, x2, y2, color, line_width)

    def draw_text(
        self,
        text: str,
        x: float,
        y: float,
        color: str = "#f0f0f0",
        font: str = "13px 'JetBrains Mono', 'Menlo', 'Consolas', monospace",
    ) -> None:
        self.backend.draw_text(text, x, y, color, font)

    def measure_text(
        self,
        text: str,
        font: str = "13px 'JetBrains Mono', 'Menlo', 'Consolas', monospace",
    ) -> float:
        return self.backend.measure_text(text, font)

    def blit_form(self, form: Form, x: float, y: float) -> None:
        self.backend.blit_form(form, x, y)
