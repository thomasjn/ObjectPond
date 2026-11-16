import base64
import io
from typing import Any, Optional, Tuple

from .canvas import DisplayCanvas
from .morph import Morph


class HexEditorMorph(Morph):
    """
    Interactive Hex & ASCII stream editor Morph.
    Acts as both a stream sink (left input port) and stream source (right output port):
    connect a FileMorph/UrlMorph (or another HexEditorMorph) into it, edit bytes
    live, and drag its output port to any downstream consumer (e.g. PipeOrganMorph).
    """

    PORT_RADIUS = 7.0
    PORT_HIT_RADIUS = 14.0
    BYTES_PER_ROW = 16
    ROW_HEIGHT = 18.0
    HEADER_HEIGHT = 30.0
    FOOTER_HEIGHT = 24.0
    _transient_attrs = ("_buffer", "_nibble_hi")

    def __init__(
        self,
        x: float = 180,
        y: float = 120,
        width: float = 548,
        height: float = 310,
        data: Optional[bytes] = None,
    ):
        super().__init__(
            x=x,
            y=y,
            width=width,
            height=height,
            color="#1e222a",
            border_color="#5e81ac",
            border_width=1.5,
        )
        self.corner_radius = 8.0
        self.source_ref: Optional[Any] = None
        self._buffer: bytearray = bytearray(data or b"")
        self._edited_b64: Optional[str] = (
            base64.b64encode(data).decode("ascii") if data is not None else None
        )
        self.dirty: bool = False
        self.scroll_row: int = 0
        self.selected_offset: Optional[int] = 0 if self._buffer else None
        self._nibble_hi: Optional[int] = None

    # --- Port & Stream Protocol ---

    def input_port_center(self) -> Tuple[float, float]:
        return (self.x + 2.0, self.y + self.height * 0.5)

    def output_port_center(self) -> Tuple[float, float]:
        return (self.x + self.width - 2.0, self.y + self.height * 0.5)

    def is_on_output_port(self, px: float, py: float) -> bool:
        cx, cy = self.output_port_center()
        return ((px - cx) ** 2 + (py - cy) ** 2) <= (self.PORT_HIT_RADIUS ** 2)

    def wants_mouse_drag(self, px: float, py: float) -> bool:
        return self.is_on_output_port(px, py)

    def accepts_stream(self, source: Any) -> bool:
        return hasattr(source, "open_stream") or hasattr(source, "reference")

    def _ensure_buffer(self) -> bytearray:
        buf = getattr(self, "_buffer", None)
        if buf is None or (len(buf) == 0 and (self._edited_b64 or self.source_ref is not None)):
            if self._edited_b64:
                self._buffer = bytearray(base64.b64decode(self._edited_b64.encode("ascii")))
            elif self.source_ref is not None:
                self._buffer = bytearray(self.source_ref.open_stream().read())
            else:
                self._buffer = bytearray()
        return self._buffer

    def connect_stream(self, ref: Any) -> None:
        self.source_ref = ref
        data = ref.open_stream().read()
        self._buffer = bytearray(data)
        self._edited_b64 = None
        self.dirty = False
        self.scroll_row = 0
        self.selected_offset = 0 if self._buffer else None
        self._nibble_hi = None
        self._push_to_downstream()
        self.changed()

    def disconnect_stream(self, ref: Any = None) -> None:
        self.source_ref = None
        self._buffer = bytearray()
        self._edited_b64 = None
        self.dirty = False
        self.selected_offset = None
        self._nibble_hi = None
        self._push_to_downstream()
        self.changed()

    def read_bytes(self, force_refresh: bool = False) -> bytes:
        if force_refresh and self.source_ref is not None and not self.dirty:
            self._buffer = bytearray(self.source_ref.open_stream(force_refresh=True).read())
        return bytes(self._ensure_buffer())

    def open_stream(self, force_refresh: bool = False) -> io.BytesIO:
        return io.BytesIO(self.read_bytes(force_refresh=force_refresh))

    def display_name(self) -> str:
        src_name = (
            self.source_ref.display_name()
            if self.source_ref is not None and hasattr(self.source_ref, "display_name")
            else "buffer"
        )
        return f"hex:{src_name}"

    def _push_to_downstream(self) -> None:
        w = self.world()
        if w is None:
            return
        for conn in list(getattr(w, "connections", [])):
            if conn.source is self and hasattr(conn.target, "connect_stream"):
                conn.target.connect_stream(self)

    def _commit_byte(self, offset: int, val: int) -> None:
        buf = self._ensure_buffer()
        if 0 <= offset < len(buf):
            buf[offset] = val & 0xFF
            self.dirty = True
            self._edited_b64 = base64.b64encode(bytes(buf)).decode("ascii")
            self._push_to_downstream()
            self.changed()

    def revert(self) -> None:
        if self.source_ref is not None:
            self.connect_stream(self.source_ref)

    # --- Layout & Input ---

    def _visible_rows(self) -> int:
        usable = max(self.ROW_HEIGHT, self.height - self.HEADER_HEIGHT - self.FOOTER_HEIGHT - 8.0)
        return max(1, int(usable // self.ROW_HEIGHT))

    def _total_rows(self) -> int:
        buf = self._ensure_buffer()
        if not buf:
            return 0
        return (len(buf) + self.BYTES_PER_ROW - 1) // self.BYTES_PER_ROW

    def _ensure_selected_visible(self) -> None:
        if self.selected_offset is None:
            return
        row = self.selected_offset // self.BYTES_PER_ROW
        vis = self._visible_rows()
        if row < self.scroll_row:
            self.scroll_row = row
        elif row >= self.scroll_row + vis:
            self.scroll_row = max(0, row - vis + 1)

    def _revert_btn_rect(self) -> Tuple[float, float, float, float]:
        return (self.x + self.width - 122.0, self.y + 5.0, 54.0, 20.0)

    def _push_btn_rect(self) -> Tuple[float, float, float, float]:
        return (self.x + self.width - 62.0, self.y + 5.0, 52.0, 20.0)

    def _point_in_rect(self, px: float, py: float, rect: Tuple[float, float, float, float]) -> bool:
        rx, ry, rw, rh = rect
        return rx <= px <= rx + rw and ry <= py <= ry + rh

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        w = self.world()
        if self.is_on_output_port(px, py):
            if w is not None and hasattr(w, "begin_connection"):
                w.begin_connection(self, px, py)
            return

        if self._point_in_rect(px, py, self._revert_btn_rect()):
            self.revert()
            return
        if self._point_in_rect(px, py, self._push_btn_rect()):
            self._push_to_downstream()
            self.changed()
            return

        buf = self._ensure_buffer()
        if not buf:
            return
        body_y = self.y + self.HEADER_HEIGHT + 6.0
        if py < body_y or py > self.y + self.height - self.FOOTER_HEIGHT:
            return
        row_idx = self.scroll_row + int((py - body_y) // self.ROW_HEIGHT)
        if row_idx < 0 or row_idx >= self._total_rows():
            return

        hex_x0 = self.x + 76.0
        hex_col_w = 21.0
        ascii_x0 = hex_x0 + self.BYTES_PER_ROW * hex_col_w + 10.0
        ascii_col_w = 7.2

        col = None
        if hex_x0 <= px < hex_x0 + self.BYTES_PER_ROW * hex_col_w:
            col = int((px - hex_x0) // hex_col_w)
        elif ascii_x0 <= px < ascii_x0 + self.BYTES_PER_ROW * ascii_col_w:
            col = int((px - ascii_x0) // ascii_col_w)

        if col is not None:
            off = row_idx * self.BYTES_PER_ROW + col
            if off < len(buf):
                self.selected_offset = off
                self._nibble_hi = None
                self.changed()

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        max_scroll = max(0, self._total_rows() - self._visible_rows())
        step = 3 if delta_y > 0 else -3
        self.scroll_row = max(0, min(max_scroll, self.scroll_row + step))
        self.changed()

    def on_key_down(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> None:
        buf = self._ensure_buffer()
        if not buf:
            return
        if self.selected_offset is None:
            self.selected_offset = 0

        if key == "ArrowRight":
            self.selected_offset = min(len(buf) - 1, self.selected_offset + 1)
            self._nibble_hi = None
        elif key == "ArrowLeft":
            self.selected_offset = max(0, self.selected_offset - 1)
            self._nibble_hi = None
        elif key == "ArrowDown":
            self.selected_offset = min(len(buf) - 1, self.selected_offset + self.BYTES_PER_ROW)
            self._nibble_hi = None
        elif key == "ArrowUp":
            self.selected_offset = max(0, self.selected_offset - self.BYTES_PER_ROW)
            self._nibble_hi = None
        elif len(key) == 1 and key.lower() in "0123456789abcdef" and not (ctrl_key or meta_key):
            nib = int(key, 16)
            if self._nibble_hi is None:
                self._nibble_hi = nib
                new_val = (nib << 4) | (buf[self.selected_offset] & 0x0F)
                self._commit_byte(self.selected_offset, new_val)
            else:
                new_val = (self._nibble_hi << 4) | nib
                self._nibble_hi = None
                self._commit_byte(self.selected_offset, new_val)
                if self.selected_offset + 1 < len(buf):
                    self.selected_offset += 1
        self._ensure_selected_visible()
        self.changed()

    # --- Drawing ---

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius,
            self.color, self.border_color, self.border_width,
        )

        # Header
        canvas.fill_round_rect(self.x + 4, self.y + 4, self.width - 8, self.HEADER_HEIGHT - 4, 5.0, "#252b37", "#3b4252", 1.0)
        buf = self._ensure_buffer()
        src_name = (
            self.source_ref.display_name()
            if self.source_ref is not None and hasattr(self.source_ref, "display_name")
            else "No stream connected"
        )
        dirty_mark = "*" if self.dirty else ""
        title = f"HexEditor: {src_name}{dirty_mark} ({len(buf):,} B)"
        canvas.draw_text(title, self.x + 12, self.y + 21, color="#88c0d0", font="bold 11px sans-serif")

        # Header buttons (Revert, Push ->)
        rx, ry, rw, rh = self._revert_btn_rect()
        canvas.fill_round_rect(rx, ry, rw, rh, 4.0, "#3b4252", "#4c566a", 1.0)
        canvas.draw_text("Revert", rx + 9, ry + 14, color="#eceff4", font="10px sans-serif")

        px_b, py_b, pw_b, ph_b = self._push_btn_rect()
        canvas.fill_round_rect(px_b, py_b, pw_b, ph_b, 4.0, "#2a4d3e", "#a3be8c", 1.0)
        canvas.draw_text("Push ➔", px_b + 7, py_b + 14, color="#a3be8c", font="bold 10px sans-serif")

        # Body
        body_y = self.y + self.HEADER_HEIGHT + 6.0
        vis_rows = self._visible_rows()
        if not buf:
            canvas.draw_text(
                "Drag a connection arrow from a FileMorph/UrlMorph into the left port.",
                self.x + 24, body_y + 30, color="#81a1c1", font="12px sans-serif",
            )
        else:
            hex_x0 = self.x + 76.0
            hex_col_w = 21.0
            ascii_x0 = hex_x0 + self.BYTES_PER_ROW * hex_col_w + 10.0
            ascii_col_w = 7.2
            tot_rows = self._total_rows()
            self.scroll_row = max(0, min(max(0, tot_rows - vis_rows), self.scroll_row))

            for r in range(vis_rows):
                row_idx = self.scroll_row + r
                if row_idx >= tot_rows:
                    break
                base_off = row_idx * self.BYTES_PER_ROW
                ry_text = body_y + r * self.ROW_HEIGHT + 13.0
                canvas.draw_text(f"{base_off:06X}:", self.x + 14, ry_text, color="#616e88", font="11px monospace")

                for c in range(self.BYTES_PER_ROW):
                    off = base_off + c
                    if off >= len(buf):
                        break
                    bval = buf[off]
                    hx = hex_x0 + c * hex_col_w
                    ax = ascii_x0 + c * ascii_col_w
                    is_sel = (off == self.selected_offset)
                    if is_sel:
                        canvas.fill_round_rect(hx - 2, ry_text - 11, 19, 14, 2.0, "#4c566a", "#ebcb8b", 1.0)
                        canvas.fill_rect(ax - 1, ry_text - 11, 8, 14, "#4c566a")
                    h_col = "#ebcb8b" if is_sel else ("#d8dee9" if bval != 0 else "#5c6678")
                    canvas.draw_text(f"{bval:02X}", hx, ry_text, color=h_col, font="11px monospace")
                    ch = chr(bval) if 32 <= bval <= 126 else "."
                    a_col = "#ebcb8b" if is_sel else ("#a3be8c" if 32 <= bval <= 126 else "#4c566a")
                    canvas.draw_text(ch, ax, ry_text, color=a_col, font="11px monospace")

        # Footer
        fy = self.y + self.height - 8.0
        if self.selected_offset is not None and 0 <= self.selected_offset < len(buf):
            b = buf[self.selected_offset]
            info = f"Offset 0x{self.selected_offset:06X} ({self.selected_offset})  Dec: {b}  Hex: 0x{b:02X}  Bin: {b:08b}"
        else:
            info = "Click any byte & type 0-9 / A-F to edit"
        canvas.draw_text(info, self.x + 14, fy, color="#aeb7c6", font="10px monospace")

        # Input port (left) and Output port (right)
        ix, iy = self.input_port_center()
        canvas.fill_circle(ix, iy, 6.0, "#88c0d0", "#14171d", 1.5)
        ox, oy = self.output_port_center()
        canvas.fill_circle(ox, oy, self.PORT_RADIUS, "#d4af37", "#14171d", 1.6)
        canvas.fill_circle(ox, oy, 2.5, "#eceff4", "", 0.0)
