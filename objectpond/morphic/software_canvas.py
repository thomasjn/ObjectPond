import io
import struct
import zlib
from typing import Dict, List, Optional, Tuple
from objectpond.morphic.canvas import DisplayCanvas, Form

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


_NAMED_COLORS: Dict[str, int] = {
    "white": 0xFFFFFFFF,
    "black": 0xFF000000,
    "red": 0xFFFF0000,
    "green": 0xFF00FF00,
    "blue": 0xFF0000FF,
    "yellow": 0xFFFFFF00,
    "cyan": 0xFF00FFFF,
    "magenta": 0xFFFF00FF,
    "gray": 0xFF808080,
    "grey": 0xFF808080,
    "transparent": 0x00000000,
}

# Compact 5x7 bitmap font (5 columns of 7-bit bitmasks, LSB = top row) for ASCII 32..126
_FONT_5X7: Dict[str, Tuple[int, ...]] = {
    " ": (0x00, 0x00, 0x00, 0x00, 0x00),
    "!": (0x00, 0x00, 0x5F, 0x00, 0x00),
    '"': (0x00, 0x07, 0x00, 0x07, 0x00),
    "#": (0x14, 0x7F, 0x14, 0x7F, 0x14),
    "$": (0x24, 0x2A, 0x7F, 0x2A, 0x12),
    "%": (0x23, 0x13, 0x08, 0x64, 0x62),
    "&": (0x36, 0x49, 0x55, 0x22, 0x50),
    "'": (0x00, 0x05, 0x03, 0x00, 0x00),
    "(": (0x00, 0x1C, 0x22, 0x41, 0x00),
    ")": (0x00, 0x41, 0x22, 0x1C, 0x00),
    "*": (0x14, 0x08, 0x3E, 0x08, 0x14),
    "+": (0x08, 0x08, 0x3E, 0x08, 0x08),
    ",": (0x00, 0x50, 0x30, 0x00, 0x00),
    "-": (0x08, 0x08, 0x08, 0x08, 0x08),
    ".": (0x00, 0x60, 0x60, 0x00, 0x00),
    "/": (0x20, 0x10, 0x08, 0x04, 0x02),
    "0": (0x3E, 0x51, 0x49, 0x45, 0x3E),
    "1": (0x00, 0x42, 0x7F, 0x40, 0x00),
    "2": (0x42, 0x61, 0x51, 0x49, 0x46),
    "3": (0x21, 0x41, 0x45, 0x4B, 0x31),
    "4": (0x18, 0x14, 0x12, 0x7F, 0x10),
    "5": (0x27, 0x45, 0x45, 0x45, 0x39),
    "6": (0x3C, 0x4A, 0x49, 0x49, 0x30),
    "7": (0x01, 0x71, 0x09, 0x05, 0x03),
    "8": (0x36, 0x49, 0x49, 0x49, 0x36),
    "9": (0x06, 0x49, 0x49, 0x29, 0x1E),
    ":": (0x00, 0x36, 0x36, 0x00, 0x00),
    ";": (0x00, 0x56, 0x36, 0x00, 0x00),
    "<": (0x08, 0x14, 0x22, 0x41, 0x00),
    "=": (0x14, 0x14, 0x14, 0x14, 0x14),
    ">": (0x00, 0x41, 0x22, 0x14, 0x08),
    "?": (0x02, 0x01, 0x51, 0x09, 0x06),
    "@": (0x32, 0x49, 0x79, 0x41, 0x3E),
    "A": (0x7E, 0x11, 0x11, 0x11, 0x7E),
    "B": (0x7F, 0x49, 0x49, 0x49, 0x36),
    "C": (0x3E, 0x41, 0x41, 0x41, 0x22),
    "D": (0x7F, 0x41, 0x41, 0x22, 0x1C),
    "E": (0x7F, 0x49, 0x49, 0x49, 0x41),
    "F": (0x7F, 0x09, 0x09, 0x09, 0x01),
    "G": (0x3E, 0x41, 0x49, 0x49, 0x7A),
    "H": (0x7F, 0x08, 0x08, 0x08, 0x7F),
    "I": (0x00, 0x41, 0x7F, 0x41, 0x00),
    "J": (0x20, 0x40, 0x41, 0x3F, 0x01),
    "K": (0x7F, 0x08, 0x14, 0x22, 0x41),
    "L": (0x7F, 0x40, 0x40, 0x40, 0x40),
    "M": (0x7F, 0x02, 0x0C, 0x02, 0x7F),
    "N": (0x7F, 0x04, 0x08, 0x10, 0x7F),
    "O": (0x3E, 0x41, 0x41, 0x41, 0x3E),
    "P": (0x7F, 0x09, 0x09, 0x09, 0x06),
    "Q": (0x3E, 0x41, 0x51, 0x21, 0x5E),
    "R": (0x7F, 0x09, 0x19, 0x29, 0x46),
    "S": (0x46, 0x49, 0x49, 0x49, 0x31),
    "T": (0x01, 0x01, 0x7F, 0x01, 0x01),
    "U": (0x3F, 0x40, 0x40, 0x40, 0x3F),
    "V": (0x1F, 0x20, 0x40, 0x20, 0x1F),
    "W": (0x3F, 0x40, 0x38, 0x40, 0x3F),
    "X": (0x63, 0x14, 0x08, 0x14, 0x63),
    "Y": (0x07, 0x08, 0x70, 0x08, 0x07),
    "Z": (0x61, 0x51, 0x49, 0x45, 0x43),
    "[": (0x00, 0x7F, 0x41, 0x41, 0x00),
    "\\": (0x02, 0x04, 0x08, 0x10, 0x20),
    "]": (0x00, 0x41, 0x41, 0x7F, 0x00),
    "^": (0x04, 0x02, 0x01, 0x02, 0x04),
    "_": (0x40, 0x40, 0x40, 0x40, 0x40),
    "`": (0x00, 0x01, 0x02, 0x04, 0x00),
    "a": (0x20, 0x54, 0x54, 0x54, 0x78),
    "b": (0x7F, 0x48, 0x44, 0x44, 0x38),
    "c": (0x38, 0x44, 0x44, 0x44, 0x20),
    "d": (0x38, 0x44, 0x44, 0x48, 0x7F),
    "e": (0x38, 0x54, 0x54, 0x54, 0x18),
    "f": (0x08, 0x7E, 0x09, 0x01, 0x02),
    "g": (0x0C, 0x52, 0x52, 0x52, 0x3E),
    "h": (0x7F, 0x08, 0x04, 0x04, 0x78),
    "i": (0x00, 0x44, 0x7D, 0x40, 0x00),
    "j": (0x20, 0x40, 0x44, 0x3D, 0x00),
    "k": (0x7F, 0x10, 0x28, 0x44, 0x00),
    "l": (0x00, 0x41, 0x7F, 0x40, 0x00),
    "m": (0x7C, 0x04, 0x18, 0x04, 0x78),
    "n": (0x7C, 0x08, 0x04, 0x04, 0x78),
    "o": (0x38, 0x44, 0x44, 0x44, 0x38),
    "p": (0x7C, 0x14, 0x14, 0x14, 0x08),
    "q": (0x08, 0x14, 0x14, 0x18, 0x7C),
    "r": (0x7C, 0x08, 0x04, 0x04, 0x08),
    "s": (0x48, 0x54, 0x54, 0x54, 0x20),
    "t": (0x04, 0x3F, 0x44, 0x40, 0x20),
    "u": (0x3C, 0x40, 0x40, 0x20, 0x7C),
    "v": (0x1C, 0x20, 0x40, 0x20, 0x1C),
    "w": (0x3C, 0x40, 0x30, 0x40, 0x3C),
    "x": (0x44, 0x28, 0x10, 0x28, 0x44),
    "y": (0x0C, 0x50, 0x50, 0x50, 0x3C),
    "z": (0x44, 0x64, 0x54, 0x4C, 0x44),
    "{": (0x00, 0x08, 0x36, 0x41, 0x00),
    "|": (0x00, 0x00, 0x7F, 0x00, 0x00),
    "}": (0x00, 0x41, 0x36, 0x08, 0x00),
    "~": (0x10, 0x08, 0x08, 0x10, 0x08),
}


def parse_css_color(color: Optional[str]) -> int:
    """Parses a CSS hex/rgb/rgba/named color string into 0xAARRGGBB."""
    if not color:
        return 0x00000000
    s = color.strip().lower()
    if s in _NAMED_COLORS:
        return _NAMED_COLORS[s]
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            r, g, b = (int(c * 2, 16) for c in h)
            return (0xFF << 24) | (r << 16) | (g << 8) | b
        if len(h) == 6:
            val = int(h, 16)
            return 0xFF000000 | val
        if len(h) == 8:
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            a = int(h[6:8], 16)
            return (a << 24) | (r << 16) | (g << 8) | b
    if s.startswith("rgba(") and s.endswith(")"):
        parts = [p.strip() for p in s[5:-1].split(",")]
        if len(parts) == 4:
            r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
            a_raw = float(parts[3])
            a = int(a_raw * 255) if a_raw <= 1.0 else int(a_raw)
            return ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
    if s.startswith("rgb(") and s.endswith(")"):
        parts = [p.strip() for p in s[4:-1].split(",")]
        if len(parts) == 3:
            r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
            return (0xFF << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
    return 0xFFFFFFFF


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def form_to_png_bytes(form: Form) -> bytes:
    """Encodes a 32-bit Form (0xAARRGGBB pixels) into a PNG byte stream using stdlib zlib."""
    w, h = form.width, form.height
    raw_bytes = form.to_bytes()
    stride = w * 4
    scanlines = bytearray()
    for y in range(h):
        scanlines.append(0)  # Filter type 0 (None)
        row_start = y * stride
        for x in range(w):
            i = row_start + x * 4
            # Little-endian 0xAARRGGBB -> bytes [B, G, R, A] -> PNG RGBA [R, G, B, A]
            scanlines.append(raw_bytes[i + 2])
            scanlines.append(raw_bytes[i + 1])
            scanlines.append(raw_bytes[i])
            scanlines.append(raw_bytes[i + 3])

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(scanlines), level=6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


class SoftwareCanvasBackend:
    """Pure-Python DisplayCanvas backend rendering onto a Form buffer (no external deps)."""

    def __init__(self, width: int = 1280, height: int = 800):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.form = Form(self.width, self.height, 0xFF242933)
        self._clip_stack: List[Tuple[int, int, int, int]] = []

    def _current_clip(self) -> Tuple[int, int, int, int]:
        if not self._clip_stack:
            return (0, 0, self.width, self.height)
        return self._clip_stack[-1]

    def _put_clipped(self, x: int, y: int, color32: int) -> None:
        if (color32 >> 24) == 0:
            return
        cx0, cy0, cx1, cy1 = self._current_clip()
        if cx0 <= x < cx1 and cy0 <= y < cy1:
            alpha = (color32 >> 24) & 0xFF
            if alpha == 255:
                self.form.pixels[y * self.width + x] = color32
            else:
                bg = self.form.pixels[y * self.width + x]
                inv = 255 - alpha
                r = (((color32 >> 16) & 0xFF) * alpha + ((bg >> 16) & 0xFF) * inv) // 255
                g = (((color32 >> 8) & 0xFF) * alpha + ((bg >> 8) & 0xFF) * inv) // 255
                b = ((color32 & 0xFF) * alpha + (bg & 0xFF) * inv) // 255
                self.form.pixels[y * self.width + x] = (0xFF << 24) | (r << 16) | (g << 8) | b

    def save_clip(self, x: float, y: float, w: float, h: float) -> None:
        px0, py0, px1, py1 = self._current_clip()
        nx0 = max(px0, int(x))
        ny0 = max(py0, int(y))
        nx1 = min(px1, int(x + w))
        ny1 = min(py1, int(y + h))
        self._clip_stack.append((nx0, ny0, max(nx0, nx1), max(ny0, ny1)))

    def restore_clip(self) -> None:
        if self._clip_stack:
            self._clip_stack.pop()

    def fill_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        c32 = parse_css_color(color)
        if (c32 >> 24) == 0:
            return
        cx0, cy0, cx1, cy1 = self._current_clip()
        x0 = max(cx0, int(x))
        y0 = max(cy0, int(y))
        x1 = min(cx1, int(x + w))
        y1 = min(cy1, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        if (c32 >> 24) == 255:
            self.form.fill_rect(x0, y0, x1 - x0, y1 - y0, c32)
        else:
            for py in range(y0, y1):
                for px in range(x0, x1):
                    self._put_clipped(px, py, c32)

    def stroke_rect(self, x: float, y: float, w: float, h: float, color: str, line_width: float = 1.0) -> None:
        lw = max(1, int(round(line_width)))
        self.fill_rect(x, y, w, lw, color)
        self.fill_rect(x, y + h - lw, w, lw, color)
        self.fill_rect(x, y, lw, h, color)
        self.fill_rect(x + w - lw, y, lw, h, color)

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
        if fill_color:
            self.fill_rect(x, y, w, h, fill_color)
        if stroke_color:
            self.stroke_rect(x, y, w, h, stroke_color, line_width)

    def fill_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        fill_color: str,
        stroke_color: Optional[str] = None,
        line_width: float = 1.0,
    ) -> None:
        r = max(1.0, float(radius))
        r2 = r * r
        fill32 = parse_css_color(fill_color) if fill_color else 0
        stroke32 = parse_css_color(stroke_color) if stroke_color else 0
        inner_r2 = max(0.0, (r - max(1.0, line_width)) ** 2)
        icx, icy, ir = int(cx), int(cy), int(r) + 1
        for dy in range(-ir, ir + 1):
            for dx in range(-ir, ir + 1):
                d2 = dx * dx + dy * dy
                if d2 <= r2:
                    if stroke32 and d2 >= inner_r2:
                        self._put_clipped(icx + dx, icy + dy, stroke32)
                    elif fill32:
                        self._put_clipped(icx + dx, icy + dy, fill32)

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, color: str, line_width: float = 1.0) -> None:
        c32 = parse_css_color(color)
        ix1, iy1, ix2, iy2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
        dx = abs(ix2 - ix1)
        dy = -abs(iy2 - iy1)
        sx = 1 if ix1 < ix2 else -1
        sy = 1 if iy1 < iy2 else -1
        err = dx + dy
        while True:
            self._put_clipped(ix1, iy1, c32)
            if ix1 == ix2 and iy1 == iy2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                ix1 += sx
            if e2 <= dx:
                err += dx
                iy1 += sy

    def draw_text(
        self,
        text: str,
        x: float,
        y: float,
        color: str = "#ffffff",
        font: str = "13px monospace",
    ) -> None:
        c32 = parse_css_color(color)
        # Canvas drawText uses baseline y; offset upward by ~9px for 5x7 glyph top
        top_y = int(round(y)) - 9
        cur_x = int(round(x))
        for ch in str(text):
            glyph = _FONT_5X7.get(ch)
            if glyph:
                for col_idx, col_mask in enumerate(glyph):
                    for row_idx in range(7):
                        if col_mask & (1 << row_idx):
                            self._put_clipped(cur_x + col_idx, top_y + row_idx, c32)
            cur_x += 7

    def measure_text(self, text: str, font: str = "13px monospace") -> float:
        return len(str(text)) * 7.0

    def blit_form(self, form: Form, x: float, y: float) -> None:
        self.form.copy_bits(form, 0, 0, form.width, form.height, int(x), int(y))

    def to_png_bytes(self) -> bytes:
        return form_to_png_bytes(self.form)


class PILCanvasBackend:
    """Optional Pillow-based headless backend used when PIL is available."""

    def __init__(self, width: int = 1280, height: int = 800):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.image = Image.new("RGBA", (self.width, self.height), (36, 41, 51, 255))
        self.draw = ImageDraw.Draw(self.image)
        self._clip_stack: List[Tuple[int, int, int, int]] = []
        self._font = ImageFont.load_default()

    @staticmethod
    def _rgba(color: str) -> Tuple[int, int, int, int]:
        c = parse_css_color(color)
        return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF, (c >> 24) & 0xFF)

    def save_clip(self, x: float, y: float, w: float, h: float) -> None:
        self._clip_stack.append((int(x), int(y), int(w), int(h)))

    def restore_clip(self) -> None:
        if self._clip_stack:
            self._clip_stack.pop()

    def fill_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        if w > 0 and h > 0:
            self.draw.rectangle([x, y, x + w, y + h], fill=self._rgba(color))

    def stroke_rect(self, x: float, y: float, w: float, h: float, color: str, line_width: float = 1.0) -> None:
        if w > 0 and h > 0:
            self.draw.rectangle([x, y, x + w, y + h], outline=self._rgba(color), width=max(1, int(line_width)))

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
        fill = self._rgba(fill_color) if fill_color else None
        outline = self._rgba(stroke_color) if stroke_color else None
        self.draw.rounded_rectangle(
            [x, y, x + w, y + h],
            radius=max(0, radius),
            fill=fill,
            outline=outline,
            width=max(1, int(line_width)),
        )

    def fill_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        fill_color: str,
        stroke_color: Optional[str] = None,
        line_width: float = 1.0,
    ) -> None:
        r = max(0.5, radius)
        fill = self._rgba(fill_color) if fill_color else None
        outline = self._rgba(stroke_color) if stroke_color else None
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=max(1, int(line_width)))

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, color: str, line_width: float = 1.0) -> None:
        self.draw.line([x1, y1, x2, y2], fill=self._rgba(color), width=max(1, int(line_width)))

    def draw_text(
        self,
        text: str,
        x: float,
        y: float,
        color: str = "#ffffff",
        font: str = "13px monospace",
    ) -> None:
        self.draw.text((x, y - 11), str(text), fill=self._rgba(color), font=self._font)

    def measure_text(self, text: str, font: str = "13px monospace") -> float:
        return len(str(text)) * 7.2

    def blit_form(self, form: Form, x: float, y: float) -> None:
        raw = form.to_bytes()
        rgba = bytearray(len(raw))
        for i in range(0, len(raw), 4):
            rgba[i] = raw[i + 2]
            rgba[i + 1] = raw[i + 1]
            rgba[i + 2] = raw[i]
            rgba[i + 3] = raw[i + 3]
        sub = Image.frombytes("RGBA", (form.width, form.height), bytes(rgba))
        self.image.alpha_composite(sub, (int(x), int(y)))

    def to_png_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.image.save(buf, format="PNG")
        return buf.getvalue()


def render_world_png(world: object) -> bytes:
    """Renders a WorldMorph headlessly into PNG bytes (PIL if installed, else pure-Python Form)."""
    w = int(getattr(world, "width", 1280))
    h = int(getattr(world, "height", 800))
    backend = PILCanvasBackend(w, h) if _HAS_PIL else SoftwareCanvasBackend(w, h)
    canvas = DisplayCanvas(backend)
    world.full_draw_on(canvas)  # type: ignore[attr-defined]
    return backend.to_png_bytes()
