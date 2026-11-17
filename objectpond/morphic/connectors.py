import math
import time
from typing import Any, Optional, Tuple

from .canvas import DisplayCanvas
from .morph import Morph
from ..kernel.references import ExternalReference, FileReference, UrlReference


class ResourceIconMorph(Morph):
    """
    Windows-style desktop icon representing an external FileReference or UrlReference.
    Drag the body to move it on the desktop; drag from the right-edge output port
    to draw a streaming ConnectionArrowMorph to another Morph.
    """

    PORT_RADIUS = 7.0
    PORT_HIT_RADIUS = 14.0
    _transient_attrs = ("_down_pos", "_last_click_ts")

    def __init__(
        self,
        reference: Optional[ExternalReference] = None,
        x: float = 80,
        y: float = 80,
        width: float = 98,
        height: float = 92,
    ):
        super().__init__(
            x=x,
            y=y,
            width=width,
            height=height,
            color="#252b37",
            border_color="#4c566a",
            border_width=1.2,
        )
        self.corner_radius = 8.0
        self.reference = reference
        self._down_pos: Optional[Tuple[float, float]] = None
        self._last_click_ts: float = 0.0

    def output_port_center(self) -> Tuple[float, float]:
        return (self.x + self.width - 2.0, self.y + self.height * 0.42)

    def is_on_output_port(self, px: float, py: float) -> bool:
        cx, cy = self.output_port_center()
        return ((px - cx) ** 2 + (py - cy) ** 2) <= (self.PORT_HIT_RADIUS ** 2)

    def wants_mouse_drag(self, px: float, py: float) -> bool:
        return self.is_on_output_port(px, py)

    def open_stream(self, force_refresh: bool = False):
        if self.reference is None:
            raise ValueError("No ExternalReference attached")
        return self.reference.open_stream(force_refresh=force_refresh)

    def read_bytes(self, force_refresh: bool = False) -> bytes:
        if self.reference is None:
            raise ValueError("No ExternalReference attached")
        return self.reference.read_bytes(force_refresh=force_refresh)

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        w = self.world()
        if self.is_on_output_port(px, py):
            if w is not None and hasattr(w, "begin_connection"):
                w.begin_connection(self, px, py)
            return
        self._down_pos = (px, py)

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        if button != 0 or getattr(self, "_down_pos", None) is None:
            return
        dx = px - self._down_pos[0]
        dy = py - self._down_pos[1]
        self._down_pos = None
        if (dx * dx + dy * dy) <= 25.0:
            now = time.monotonic()
            if now - getattr(self, "_last_click_ts", 0.0) <= 0.38:
                self._last_click_ts = 0.0
                w = self.world()
                if w is not None and self.reference is not None:
                    w.open_inspector(self.reference)
            else:
                self._last_click_ts = now

    def _badge_color(self, badge: str) -> str:
        if badge in ("MID", "MIDI", "WAV"):
            return "#d4af37"
        if badge in ("MD", "MARK", "TXT", "RST"):
            return "#a3be8c"
        if badge in ("PNG", "JPG", "GIF", "BMP"):
            return "#b48ead"
        if badge in ("URL", "HTML", "JSON"):
            return "#88c0d0"
        return "#81a1c1"

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius,
            self.color, self.border_color, self.border_width,
        )

        # Document / globe icon box centered in upper area
        doc_w, doc_h = 38.0, 44.0
        doc_x = self.x + (self.width - doc_w) * 0.5 - 3.0
        doc_y = self.y + 10.0
        fold = 10.0

        badge = self.reference.extension_badge() if self.reference is not None else "FILE"
        badge_col = self._badge_color(badge)

        # Page body + dog-ear corner
        canvas.fill_round_rect(doc_x, doc_y, doc_w, doc_h, 4.0, "#eceff4", "#4c566a", 1.2)
        canvas.fill_rect(doc_x + doc_w - fold, doc_y, fold, fold, self.color)
        canvas.draw_line(doc_x + doc_w - fold, doc_y, doc_x + doc_w - fold, doc_y + fold, "#4c566a", 1.0)
        canvas.draw_line(doc_x + doc_w - fold, doc_y + fold, doc_x + doc_w, doc_y + fold, "#4c566a", 1.0)

        # Decorative lines or globe ring
        if isinstance(self.reference, UrlReference):
            gcx = doc_x + doc_w * 0.5
            gcy = doc_y + doc_h * 0.44
            canvas.fill_circle(gcx, gcy, 9.0, "#88c0d0", "#2e3440", 1.0)
            canvas.draw_line(gcx - 9.0, gcy, gcx + 9.0, gcy, "#2e3440", 0.9)
        else:
            for row in range(3):
                ly = doc_y + 13.0 + row * 6.0
                canvas.draw_line(doc_x + 7.0, ly, doc_x + doc_w - 8.0, ly, "#aeb7c6", 1.4)

        # Extension pill across lower part of icon
        pill_w = 34.0
        pill_h = 14.0
        pill_x = doc_x + (doc_w - pill_w) * 0.5
        pill_y = doc_y + doc_h - pill_h - 3.0
        canvas.fill_round_rect(pill_x, pill_y, pill_w, pill_h, 3.0, badge_col, "#1e222a", 0.8)
        bw = canvas.measure_text(badge, "bold 9px sans-serif")
        canvas.draw_text(badge, pill_x + (pill_w - bw) * 0.5, pill_y + 10.5, color="#14171d", font="bold 9px sans-serif")

        # File / URL label
        name = self.reference.display_name() if self.reference is not None else "resource"
        if len(name) > 13:
            name = name[:12] + "…"
        tw = canvas.measure_text(name, "11px sans-serif")
        tx = self.x + max(4.0, (self.width - tw) * 0.5 - 2.0)
        canvas.draw_text(name, tx, self.y + self.height - 10.0, color="#eceff4", font="11px sans-serif")

        # Output stream port on right edge
        px, py = self.output_port_center()
        canvas.fill_circle(px, py, self.PORT_RADIUS, badge_col, "#14171d", 1.6)
        canvas.fill_circle(px, py, 2.5, "#eceff4", "", 0.0)


class FileMorph(ResourceIconMorph):
    """Desktop file-icon Morph backed by a FileReference."""

    def __init__(
        self,
        reference: Optional[FileReference] = None,
        anchor: str = "assets",
        path: str = "",
        x: float = 80,
        y: float = 80,
    ):
        ref = reference if reference is not None else FileReference(anchor=anchor, path=path)
        super().__init__(reference=ref, x=x, y=y)


class UrlMorph(ResourceIconMorph):
    """Desktop URL-icon Morph backed by a UrlReference."""

    def __init__(
        self,
        reference: Optional[UrlReference] = None,
        url: str = "https://example.com",
        x: float = 80,
        y: float = 80,
    ):
        ref = reference if reference is not None else UrlReference(url=url)
        super().__init__(reference=ref, x=x, y=y)


class ConnectionArrowMorph:
    """
    Visual data-stream arrow connecting a source Morph (e.g. FileMorph/UrlMorph)
    to a target Morph (e.g. PipeOrganMorph).
    """

    def __init__(self, source: Morph, target: Morph, color: str = "#d4af37"):
        self.source = source
        self.target = target
        self.color = color

    def endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        if hasattr(self.source, "output_port_center"):
            sx, sy = self.source.output_port_center()
        else:
            sx, sy = (self.source.x + self.source.width, self.source.y + self.source.height * 0.5)

        if hasattr(self.target, "input_port_center"):
            tx, ty = self.target.input_port_center()
        else:
            tx, ty = (self.target.x, self.target.y + self.target.height * 0.5)
        return (sx, sy), (tx, ty)

    def _curve_point(self, p0: Tuple[float, float], p3: Tuple[float, float], u: float) -> Tuple[float, float]:
        sx, sy = p0
        tx, ty = p3
        span = max(48.0, abs(tx - sx) * 0.48)
        c1x, c1y = sx + span, sy
        c2x, c2y = tx - span, ty
        inv = 1.0 - u
        x = (inv ** 3) * sx + 3 * (inv ** 2) * u * c1x + 3 * inv * (u ** 2) * c2x + (u ** 3) * tx
        y = (inv ** 3) * sy + 3 * (inv ** 2) * u * c1y + 3 * inv * (u ** 2) * c2y + (u ** 3) * ty
        return (x, y)

    def midpoint(self) -> Tuple[float, float]:
        p0, p3 = self.endpoints()
        return self._curve_point(p0, p3, 0.5)

    def is_disconnect_hit(self, px: float, py: float) -> bool:
        mx, my = self.midpoint()
        return ((px - mx) ** 2 + (py - my) ** 2) <= 100.0

    def draw_on(self, canvas: DisplayCanvas) -> None:
        p0, p3 = self.endpoints()
        steps = 16
        pts = [self._curve_point(p0, p3, i / float(steps)) for i in range(steps + 1)]
        for i in range(steps):
            canvas.draw_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], self.color, 2.5)

        # Arrowhead at p3
        px_prev, py_prev = pts[-2]
        tx, ty = p3
        ang = math.atan2(ty - py_prev, tx - px_prev)
        head_len = 10.0
        for delta in (2.65, -2.65):
            hx = tx + head_len * math.cos(ang + delta)
            hy = ty + head_len * math.sin(ang + delta)
            canvas.draw_line(tx, ty, hx, hy, self.color, 2.5)

        # Animated stream pulse when target is playing/streaming
        if getattr(self.target, "is_playing", False) or getattr(self.target, "is_streaming", False):
            u = (time.monotonic() * 1.1) % 1.0
            ax, ay = self._curve_point(p0, p3, u)
            canvas.fill_circle(ax, ay, 4.5, "#ebcb8b", "#14171d", 1.2)

        # Midpoint disconnect/status badge
        mx, my = pts[steps // 2]
        canvas.fill_circle(mx, my, 8.0, "#1e222a", self.color, 1.3)
        canvas.draw_text("×", mx - 3.5, my + 3.5, color="#eceff4", font="bold 11px sans-serif")
