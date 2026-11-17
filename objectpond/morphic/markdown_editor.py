import io
import re
from typing import Any, List, Optional, Tuple

from .canvas import DisplayCanvas
from .morph import Morph
from .widgets import CodeEditorMorph

_INLINE_TOKEN_RE = re.compile(
    r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))"
)
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


def _parse_inline_spans(text: str) -> List[Tuple[str, str]]:
    """Split inline Markdown into (style, text) tuples: normal, bold, italic, code, link."""
    spans: List[Tuple[str, str]] = []
    pos = 0
    for m in _INLINE_TOKEN_RE.finditer(text):
        if m.start() > pos:
            spans.append(("normal", text[pos : m.start()]))
        tok = m.group(0)
        if tok.startswith("`") and tok.endswith("`"):
            spans.append(("code", tok[1:-1]))
        elif tok.startswith("**") and tok.endswith("**"):
            spans.append(("bold", tok[2:-2]))
        elif tok.startswith("*") and tok.endswith("*"):
            spans.append(("italic", tok[1:-1]))
        elif tok.startswith("["):
            close_br = tok.find("](")
            label = tok[1:close_br] if close_br != -1 else tok
            spans.append(("link", label))
        pos = m.end()
    if pos < len(text):
        spans.append(("normal", text[pos:]))
    return spans or [("normal", "")]


def parse_markdown_blocks(text: str) -> List[Tuple[str, Any]]:
    """Parse Markdown text into a list of lightweight block tuples."""
    blocks: List[Tuple[str, Any]] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines: List[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            blocks.append(("code_block", (lang, code_lines)))
            continue

        if not stripped:
            blocks.append(("blank", None))
            i += 1
            continue

        if _HR_RE.match(line):
            blocks.append(("hr", None))
            i += 1
            continue

        hm = _HEADING_RE.match(line)
        if hm:
            blocks.append(("heading", (len(hm.group(1)), hm.group(2).strip())))
            i += 1
            continue

        if stripped.startswith("> "):
            quote_lines: List[str] = []
            while i < n and lines[i].strip().startswith("> "):
                quote_lines.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("blockquote", " ".join(quote_lines)))
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(("bullet", stripped[2:]))
            i += 1
            continue

        om = _ORDERED_RE.match(stripped)
        if om:
            blocks.append(("ordered", (om.group(1), om.group(2))))
            i += 1
            continue

        para_lines: List[str] = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            nxt_s = nxt.strip()
            if (
                not nxt_s
                or nxt_s.startswith("```")
                or nxt_s.startswith("> ")
                or nxt_s.startswith("- ")
                or nxt_s.startswith("* ")
                or _HEADING_RE.match(nxt)
                or _ORDERED_RE.match(nxt_s)
                or _HR_RE.match(nxt)
            ):
                break
            para_lines.append(nxt_s)
            i += 1
        blocks.append(("paragraph", " ".join(para_lines)))

    return blocks


class MarkdownEditorMorph(Morph):
    """
    Stream-driven Markdown File Editor & Live Preview Morph.
    Connect any FileMorph, UrlMorph, or HexEditorMorph into its left input port.
    Supports Edit, Split, and Preview modes, live downstream streaming via its
    right output port, and saving back to anchored FileReference files.
    """

    PORT_RADIUS = 7.0
    PORT_HIT_RADIUS = 14.0
    HEADER_HEIGHT = 32.0
    FOOTER_HEIGHT = 22.0
    _transient_attrs = ("_last_synced_text", "_preview_max_scroll")

    def __init__(
        self,
        x: float = 140,
        y: float = 90,
        width: float = 640,
        height: float = 400,
        text: str = "",
        mode: str = "split",
    ):
        super().__init__(
            x=x,
            y=y,
            width=width,
            height=height,
            color="#1e222a",
            border_color="#a3be8c",
            border_width=1.6,
        )
        self.corner_radius = 8.0
        self.source_ref: Optional[Any] = None
        self.mode: str = mode if mode in ("edit", "split", "preview") else "split"
        self.dirty: bool = False
        self.preview_scroll_y: float = 0.0
        self._preview_max_scroll: float = 0.0
        self.status_note: str = "Connect a .md FileMorph"
        self._last_synced_text: str = text

        self.editor = CodeEditorMorph(
            x=self.x + 6.0,
            y=self.y + self.HEADER_HEIGHT + 4.0,
            width=max(120.0, self.width * 0.5 - 10.0),
            height=max(80.0, self.height - self.HEADER_HEIGHT - self.FOOTER_HEIGHT - 8.0),
            text=text,
        )
        self.add_morph(self.editor)
        self._layout_children()

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

    def connect_stream(self, ref: Any) -> None:
        self.source_ref = ref
        try:
            raw = ref.open_stream().read()
            text = raw.decode("utf-8", errors="replace")
            name = ref.display_name() if hasattr(ref, "display_name") else "markdown"
            self.status_note = f"Loaded {name}"
        except Exception as exc:
            text = ""
            self.status_note = f"Stream error: {exc}"
        self.editor.set_text(text)
        self._last_synced_text = text
        self.dirty = False
        self.preview_scroll_y = 0.0
        self._push_to_downstream()
        self.changed()

    def disconnect_stream(self, ref: Any = None) -> None:
        self.source_ref = None
        self.editor.set_text("")
        self._last_synced_text = ""
        self.dirty = False
        self.preview_scroll_y = 0.0
        self.status_note = "Connect a .md FileMorph"
        self._push_to_downstream()
        self.changed()

    def _sync_editor_changes(self) -> None:
        cur = self.editor.text
        if cur != getattr(self, "_last_synced_text", None):
            self._last_synced_text = cur
            self.dirty = True
            self._push_to_downstream()

    def read_bytes(self, force_refresh: bool = False) -> bytes:
        if force_refresh and self.source_ref is not None and not self.dirty:
            raw = self.source_ref.open_stream(force_refresh=True).read()
            text = raw.decode("utf-8", errors="replace")
            self.editor.set_text(text)
            self._last_synced_text = text
        return self.editor.text.encode("utf-8")

    def open_stream(self, force_refresh: bool = False) -> io.BytesIO:
        return io.BytesIO(self.read_bytes(force_refresh=force_refresh))

    def display_name(self) -> str:
        src_name = (
            self.source_ref.display_name()
            if self.source_ref is not None and hasattr(self.source_ref, "display_name")
            else "untitled.md"
        )
        return f"md:{src_name}"

    def _push_to_downstream(self) -> None:
        w = self.world()
        if w is None:
            return
        for conn in list(getattr(w, "connections", [])):
            if conn.source is self and hasattr(conn.target, "connect_stream"):
                conn.target.connect_stream(self)

    # --- Actions ---

    def set_mode(self, mode: str) -> None:
        if mode in ("edit", "split", "preview"):
            self.mode = mode
            self._layout_children()
            self.changed()

    def revert(self) -> None:
        if self.source_ref is not None:
            self.connect_stream(self.source_ref)

    def save(self) -> bool:
        self._sync_editor_changes()
        ref = getattr(self, "source_ref", None)
        if ref is None:
            self.status_note = "No connected FileReference to save"
            self.changed()
            return False
        if hasattr(ref, "write_bytes"):
            try:
                data = self.editor.text.encode("utf-8")
                ref.write_bytes(data)
                self.dirty = False
                self.editor.is_dirty = False
                self._last_synced_text = self.editor.text
                name = ref.display_name() if hasattr(ref, "display_name") else "file"
                self.status_note = f"Saved {name} ({len(data)} B)"
                self._push_to_downstream()
                self.changed()
                return True
            except Exception as exc:
                self.status_note = f"Save error: {exc}"
                self.changed()
                return False
        self._push_to_downstream()
        self.status_note = "Stream is read-only; pushed downstream"
        self.changed()
        return False

    # --- Layout ---

    def _body_rect(self) -> Tuple[float, float, float, float]:
        bx = self.x + 8.0
        by = self.y + self.HEADER_HEIGHT + 4.0
        bw = max(80.0, self.width - 16.0)
        bh = max(60.0, self.height - self.HEADER_HEIGHT - self.FOOTER_HEIGHT - 8.0)
        return (bx, by, bw, bh)

    def _preview_rect(self) -> Tuple[float, float, float, float]:
        bx, by, bw, bh = self._body_rect()
        if self.mode == "split":
            half = max(40.0, (bw - 6.0) * 0.5)
            return (bx + half + 6.0, by, bw - half - 6.0, bh)
        return (bx, by, bw, bh)

    def _layout_children(self) -> None:
        if not hasattr(self, "editor") or self.editor is None:
            return
        bx, by, bw, bh = self._body_rect()
        self.editor.on_accept = lambda _txt: self.save()
        if self.mode == "preview":
            self.editor.visible = False
        elif self.mode == "edit":
            self.editor.visible = True
            self.editor.x = bx
            self.editor.y = by
            self.editor.set_extent(bw, bh)
        else:
            self.editor.visible = True
            half = max(40.0, (bw - 6.0) * 0.5)
            self.editor.x = bx
            self.editor.y = by
            self.editor.set_extent(half, bh)

    def set_position(self, x: float, y: float) -> None:
        super().set_position(x, y)
        self._layout_children()

    def set_extent(self, w: float, h: float) -> None:
        super().set_extent(max(320.0, w), max(180.0, h))
        self._layout_children()

    def _btn_rects(self) -> List[Tuple[str, Tuple[float, float, float, float]]]:
        y = self.y + 6.0
        h = 20.0
        rx = self.x + self.width - 8.0
        buttons = [
            ("save", 46.0),
            ("revert", 50.0),
            ("preview", 56.0),
            ("split", 40.0),
            ("edit", 38.0),
        ]
        out: List[Tuple[str, Tuple[float, float, float, float]]] = []
        for name, w in buttons:
            rx -= w
            out.append((name, (rx, y, w, h)))
            rx -= 4.0
        return out

    @staticmethod
    def _point_in_rect(px: float, py: float, rect: Tuple[float, float, float, float]) -> bool:
        rx, ry, rw, rh = rect
        return rx <= px <= rx + rw and ry <= py <= ry + rh

    # --- Input ---

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button != 0:
            return
        w = self.world()
        if self.is_on_output_port(px, py):
            if w is not None and hasattr(w, "begin_connection"):
                w.begin_connection(self, px, py)
            return

        for name, rect in self._btn_rects():
            if self._point_in_rect(px, py, rect):
                if name in ("edit", "split", "preview"):
                    self.set_mode(name)
                elif name == "revert":
                    self.revert()
                elif name == "save":
                    self.save()
                return

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if self.mode in ("split", "preview") and self._point_in_rect(px, py, self._preview_rect()):
            step = 28.0 if delta_y > 0 else -28.0
            max_sc = max(0.0, getattr(self, "_preview_max_scroll", 0.0))
            self.preview_scroll_y = max(0.0, min(max_sc, self.preview_scroll_y + step))
            self.changed()

    def on_key_down(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> None:
        if (ctrl_key or meta_key) and key.lower() == "s":
            self.save()
            return
        if self.editor.visible:
            self.editor.on_key_down(key, ctrl_key=ctrl_key, meta_key=meta_key, shift_key=shift_key, alt_key=alt_key)
            self._sync_editor_changes()
            self.changed()

    # --- Markdown Preview Rendering ---

    def _span_font(self, style: str, base_size: int = 12) -> str:
        if style == "bold":
            return f"bold {base_size}px sans-serif"
        if style == "italic":
            return f"italic {base_size}px sans-serif"
        if style == "code":
            return f"{max(10, base_size - 1)}px monospace"
        return f"{base_size}px sans-serif"

    def _span_color(self, style: str, default_color: str = "#eceff4") -> str:
        if style == "code":
            return "#ebcb8b"
        if style == "link":
            return "#88c0d0"
        if style == "bold":
            return "#ffffff"
        return default_color

    def _draw_wrapped_spans(
        self,
        canvas: DisplayCanvas,
        spans: List[Tuple[str, str]],
        x0: float,
        y: float,
        max_w: float,
        base_size: int = 12,
        line_h: float = 18.0,
        default_color: str = "#eceff4",
    ) -> float:
        """Draw inline-styled spans word-wrapped within max_w. Returns next y."""
        cur_x = x0
        cur_y = y
        for style, text in spans:
            font = self._span_font(style, base_size=base_size)
            col = self._span_color(style, default_color=default_color)
            words = re.split(r"(\s+)", text)
            for word in words:
                if not word:
                    continue
                w_px = canvas.measure_text(word, font)
                if cur_x > x0 and cur_x + w_px > x0 + max_w and not word.isspace():
                    cur_x = x0
                    cur_y += line_h
                if cur_x == x0 and word.isspace():
                    continue
                if style == "code":
                    canvas.fill_round_rect(cur_x - 2.0, cur_y - base_size, w_px + 4.0, base_size + 4.0, 3.0, "#2e3440", "", 0.0)
                canvas.draw_text(word, cur_x, cur_y, color=col, font=font)
                if style == "link":
                    canvas.draw_line(cur_x, cur_y + 2.0, cur_x + w_px, cur_y + 2.0, col, 1.0)
                cur_x += w_px
        return cur_y + line_h

    def _draw_preview(self, canvas: DisplayCanvas) -> None:
        px, py, pw, ph = self._preview_rect()
        canvas.fill_round_rect(px, py, pw, ph, 4.0, "#171a21", "#3b4252", 1.0)

        blocks = parse_markdown_blocks(self.editor.text)
        pad_x = 12.0
        content_w = max(40.0, pw - pad_x * 2.0)

        canvas.push_clip(px + 1.0, py + 1.0, pw - 2.0, ph - 2.0)
        try:
            cur_y = py + 20.0 - self.preview_scroll_y
            start_y = cur_y

            if not self.editor.text.strip():
                canvas.draw_text(
                    "Connect a .md FileMorph or type Markdown to preview.",
                    px + pad_x,
                    py + 28.0,
                    color="#616e88",
                    font="12px sans-serif",
                )
                self._preview_max_scroll = 0.0
                return

            for kind, payload in blocks:
                if kind == "blank":
                    cur_y += 8.0
                elif kind == "hr":
                    canvas.draw_line(px + pad_x, cur_y - 4.0, px + pw - pad_x, cur_y - 4.0, "#4c566a", 1.2)
                    cur_y += 10.0
                elif kind == "heading":
                    level, htext = payload
                    sizes = {1: 19, 2: 16, 3: 14, 4: 13}
                    fsize = sizes.get(level, 13)
                    lh = fsize + 8.0
                    colors = {1: "#88c0d0", 2: "#81a1c1", 3: "#a3be8c", 4: "#d8dee9"}
                    cur_y = self._draw_wrapped_spans(
                        canvas,
                        [("bold", htext)],
                        px + pad_x,
                        cur_y + 2.0,
                        content_w,
                        base_size=fsize,
                        line_h=lh,
                        default_color=colors.get(level, "#eceff4"),
                    )
                    if level <= 2:
                        canvas.draw_line(px + pad_x, cur_y - lh + 6.0, px + pw - pad_x, cur_y - lh + 6.0, "#3b4252", 1.0)
                    cur_y += 4.0
                elif kind == "blockquote":
                    bar_top = cur_y - 11.0
                    next_y = self._draw_wrapped_spans(
                        canvas,
                        _parse_inline_spans(payload),
                        px + pad_x + 12.0,
                        cur_y,
                        max(30.0, content_w - 14.0),
                        base_size=12,
                        line_h=17.0,
                        default_color="#aeb7c6",
                    )
                    canvas.fill_rect(px + pad_x, bar_top, 3.0, max(14.0, next_y - bar_top - 4.0), "#5e81ac")
                    cur_y = next_y + 2.0
                elif kind == "bullet":
                    canvas.fill_circle(px + pad_x + 5.0, cur_y - 4.0, 2.5, "#a3be8c", "", 0.0)
                    cur_y = self._draw_wrapped_spans(
                        canvas,
                        _parse_inline_spans(payload),
                        px + pad_x + 15.0,
                        cur_y,
                        max(30.0, content_w - 16.0),
                        base_size=12,
                        line_h=17.0,
                    )
                elif kind == "ordered":
                    num, item_txt = payload
                    canvas.draw_text(f"{num}.", px + pad_x, cur_y, color="#88c0d0", font="bold 12px sans-serif")
                    cur_y = self._draw_wrapped_spans(
                        canvas,
                        _parse_inline_spans(item_txt),
                        px + pad_x + 20.0,
                        cur_y,
                        max(30.0, content_w - 20.0),
                        base_size=12,
                        line_h=17.0,
                    )
                elif kind == "code_block":
                    lang, code_lines = payload
                    box_h = max(24.0, len(code_lines) * 15.0 + (18.0 if lang else 10.0))
                    box_y = cur_y - 12.0
                    canvas.fill_round_rect(px + pad_x, box_y, content_w, box_h, 4.0, "#242933", "#3b4252", 1.0)
                    cy = box_y + 13.0
                    if lang:
                        canvas.draw_text(lang, px + pad_x + 8.0, cy, color="#81a1c1", font="bold 9px monospace")
                        cy += 13.0
                    for cline in code_lines:
                        canvas.draw_text(cline, px + pad_x + 8.0, cy, color="#d8dee9", font="11px monospace")
                        cy += 15.0
                    cur_y = box_y + box_h + 16.0
                else:
                    cur_y = self._draw_wrapped_spans(
                        canvas,
                        _parse_inline_spans(payload),
                        px + pad_x,
                        cur_y,
                        content_w,
                        base_size=12,
                        line_h=17.0,
                    )

            total_h = (cur_y - start_y) + 24.0
            self._preview_max_scroll = max(0.0, total_h - ph)
        finally:
            canvas.pop_clip()

    # --- Drawing ---

    def draw_on(self, canvas: DisplayCanvas) -> None:
        self._sync_editor_changes()
        self._layout_children()

        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius,
            self.color, self.border_color, self.border_width,
        )

        # Header bar
        canvas.fill_round_rect(self.x + 4, self.y + 4, self.width - 8, self.HEADER_HEIGHT - 4, 5.0, "#252b37", "#3b4252", 1.0)
        src_name = (
            self.source_ref.display_name()
            if self.source_ref is not None and hasattr(self.source_ref, "display_name")
            else "untitled.md"
        )
        dirty_mark = "*" if self.dirty else ""
        title = f"Markdown: {src_name}{dirty_mark}"
        canvas.draw_text(title, self.x + 12, self.y + 21, color="#a3be8c", font="bold 11px sans-serif")

        # Header buttons
        labels = {
            "edit": "Edit",
            "split": "Split",
            "preview": "Preview",
            "revert": "Revert",
            "save": "Save",
        }
        for name, (bx, by, bw, bh) in self._btn_rects():
            active = name == self.mode
            if name == "save":
                bg, border, fg = ("#2a4d3e", "#a3be8c", "#a3be8c")
            elif active:
                bg, border, fg = ("#4c566a", "#88c0d0", "#eceff4")
            else:
                bg, border, fg = ("#3b4252", "#4c566a", "#d8dee9")
            canvas.fill_round_rect(bx, by, bw, bh, 4.0, bg, border, 1.0)
            lbl = labels[name]
            tw = canvas.measure_text(lbl, "10px sans-serif")
            canvas.draw_text(lbl, bx + (bw - tw) * 0.5, by + 13.5, color=fg, font="10px sans-serif")

        # Preview pane (Split or Preview mode)
        if self.mode in ("split", "preview"):
            self._draw_preview(canvas)

        # Footer status
        line_count = len(self.editor.text.splitlines()) if self.editor.text else 0
        char_count = len(self.editor.text)
        footer_txt = f"{self.status_note}  |  {line_count} lines, {char_count} chars"
        canvas.draw_text(footer_txt, self.x + 12, self.y + self.height - 7.0, color="#81a1c1", font="10px sans-serif")

        # Input port (left) & Output port (right)
        ix, iy = self.input_port_center()
        in_col = "#a3be8c" if self.source_ref is not None else "#4c566a"
        canvas.fill_circle(ix, iy, self.PORT_RADIUS, in_col, "#14171d", 1.6)
        canvas.fill_circle(ix, iy, 2.5, "#eceff4", "", 0.0)

        ox, oy = self.output_port_center()
        canvas.fill_circle(ox, oy, self.PORT_RADIUS, "#88c0d0", "#14171d", 1.6)
        canvas.fill_circle(ox, oy, 2.5, "#eceff4", "", 0.0)
