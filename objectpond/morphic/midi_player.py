import array
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from .canvas import DisplayCanvas
from .midi import parse_midi_bytes
from .morph import Morph
from .sound import SampledSound, note_to_hz

_NOTE_OFFSETS = {
    "C": 0, "C#": 1, "DB": 1,
    "D": 2, "D#": 3, "EB": 3,
    "E": 4,
    "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8,
    "A": 9, "A#": 10, "BB": 10,
    "B": 11,
}
_BLACK_PCS = {1, 3, 6, 8, 10}


def _note_name_to_midi(note_name: str) -> int:
    s = str(note_name).strip().upper()
    if len(s) >= 2 and s[1] in ("#", "B"):
        name, oct_str = s[:2], s[2:]
    else:
        name, oct_str = s[:1], s[1:]
    return (int(oct_str) + 1) * 12 + _NOTE_OFFSETS[name]


class MidiPlayerMorph(Morph):
    """
    Stream-driven 88-key MIDI Player Morph.
    Connect any FileMorph, UrlMorph, or HexEditorMorph into its left input port.
    Respects MIDI note velocity for both synthesis volume and key highlight intensity,
    and displays every currently sounding note on a full 88-key piano keyboard (A0-C8).
    """

    _transient_attrs = ("_cycle_cache", "_voice_cache", "_score", "_down_pos", "_active_spans")

    def __init__(self, x: float = 120, y: float = 420, width: float = 548, height: float = 188):
        super().__init__(
            x=x,
            y=y,
            width=width,
            height=height,
            color="#1c1f26",
            border_color="#d4af37",
            border_width=1.8,
        )
        self.corner_radius = 8.0
        self.source_ref: Optional[Any] = None
        self.is_playing: bool = False
        self.start_time: float = 0.0
        self.event_cursor: int = 0
        self.active_notes: Dict[int, float] = {}
        self._active_spans: List[Tuple[float, int, float]] = []
        self.current_status: str = "Connect a .mid FileMorph"
        self._down_pos: Optional[Tuple[float, float]] = None
        self._cycle_cache: Dict[str, array.array] = {}
        self._voice_cache: Dict[Any, SampledSound] = {}
        self._score: Optional[List[Tuple]] = None

    # --- Stream Consumer Protocol ---

    def input_port_center(self) -> Tuple[float, float]:
        return (self.x + 2.0, self.y + self.height * 0.5)

    def accepts_stream(self, source: Any) -> bool:
        return hasattr(source, "open_stream") or hasattr(source, "reference")

    def _build_score(self) -> List[Tuple]:
        ref = getattr(self, "source_ref", None)
        if ref is None:
            return []
        data = ref.open_stream().read()
        if not data:
            return []
        return parse_midi_bytes(data, realize_bwv565_opening=True, include_velocity=True)

    def _get_score(self) -> List[Tuple]:
        score = getattr(self, "_score", None)
        if score is None:
            score = self._build_score()
            self._score = score
        return score

    def connect_stream(self, ref: Any) -> None:
        if self.is_playing:
            self.toggle_play()
        self.source_ref = ref
        self._score = None
        self._voice_cache = {}
        self._cycle_cache = {}
        self.is_playing = False
        self.event_cursor = 0
        self.active_notes = {}
        self._active_spans = []
        try:
            score = self._get_score()
            name = ref.display_name() if hasattr(ref, "display_name") else "MIDI"
            self.current_status = f"Loaded {name} ({len(score)} events)"
        except Exception as exc:
            self._score = []
            self.current_status = f"Stream error: {exc}"
        self.changed()

    def disconnect_stream(self, ref: Any = None) -> None:
        if self.is_playing:
            self.toggle_play()
        self.source_ref = None
        self._score = []
        self.event_cursor = 0
        self.active_notes = {}
        self._active_spans = []
        self.current_status = "Connect a .mid FileMorph"
        self.changed()

    # --- Velocity-Sensitive Wavetable Synthesis ---

    def _get_single_cycle(self, note_name: str) -> array.array:
        ccache = getattr(self, "_cycle_cache", None)
        if ccache is None:
            self._cycle_cache = {}
            ccache = self._cycle_cache
        sc = ccache.get(note_name)
        if isinstance(sc, array.array):
            return sc

        sr = 22050
        hz = note_to_hz(note_name)
        exact_p = sr / hz
        k_min = max(1, int(240.0 / exact_p))
        k_max = max(k_min + 1, int(1500.0 / exact_p))
        best_k = min(
            range(k_min, k_max + 1),
            key=lambda k: abs(k * exact_p - round(k * exact_p)) / k,
        )
        pk = max(16, int(round(best_k * exact_p)))
        partials = ((1.0, 1.0), (2.0, 0.52), (3.0, 0.28), (4.0, 0.16), (6.0, 0.08))
        norm = 2.04
        base_ang = 2.0 * math.pi * best_k / pk
        sc = array.array(
            "h",
            (
                int(
                    (sum(w * math.sin(base_ang * mult * i) for mult, w in partials) / norm)
                    * 9000.0
                )
                for i in range(pk)
            ),
        )
        ccache[note_name] = sc
        return sc

    def _synth_chord(self, note_vel_pairs: List[Tuple[str, float]], dur: float) -> SampledSound:
        sr = 22050
        dur = max(0.04, float(dur))
        dur_key = round(dur, 3)
        nv_key = tuple((n, round(float(v), 2)) for n, v in note_vel_pairs)
        key = (nv_key, dur_key)

        vcache = getattr(self, "_voice_cache", None)
        if vcache is None:
            self._voice_cache = {}
            vcache = self._voice_cache
        cached = vcache.get(key)
        if cached is not None and hasattr(cached, "samples") and isinstance(cached.samples, array.array):
            return cached

        n_samples = max(220, int(round(dur * sr)))
        att = min(180, n_samples // 4)
        rel = min(440, n_samples // 3)
        n_voices = max(1, len(note_vel_pairs))
        chord_div = max(1.0, math.sqrt(n_voices))

        buf = array.array("h", [0] * n_samples)
        for n_name, vel in note_vel_pairs:
            vel_gain = (0.12 + 0.88 * max(0.0, min(1.0, float(vel)))) / chord_div
            sc = self._get_single_cycle(n_name)
            p = len(sc)
            rep = (sc * (n_samples // p + 2))[:n_samples]
            for i in range(n_samples):
                buf[i] = max(-32767, min(32767, buf[i] + int(rep[i] * vel_gain)))

        for i in range(att):
            buf[i] = int(buf[i] * (i / float(att)))
        rel_start = n_samples - rel
        for i in range(rel):
            buf[rel_start + i] = int(buf[rel_start + i] * (1.0 - i / float(rel)))

        snd = SampledSound(buf, sample_rate=sr, channels=1)
        if dur <= 0.85 and len(vcache) < 64:
            vcache[key] = snd
        return snd

    # --- Playback & Stepping ---

    def toggle_play(self) -> bool:
        if self.is_playing:
            self.is_playing = False
            self.active_notes = {}
            self._active_spans = []
            self.current_status = "Stopped (Click to Play)"
            try:
                import js  # type: ignore

                ctx = getattr(js.window, "_objectPondAudioCtx", None)
                if ctx is not None:
                    ctx.close()
                    js.window._objectPondAudioCtx = None
            except Exception:
                pass
        else:
            score = self._get_score()
            if not score:
                self.current_status = "Connect a .mid FileMorph"
                self.changed()
                return False
            self.is_playing = True
            self.start_time = time.monotonic()
            self.event_cursor = 0
            self.active_notes = {}
            self._active_spans = []
            name = (
                self.source_ref.display_name()
                if self.source_ref is not None and hasattr(self.source_ref, "display_name")
                else "MIDI"
            )
            self.current_status = f"Playing {name}"
        self.changed()
        return self.is_playing

    def wants_steps(self) -> bool:
        return True

    def step(self) -> None:
        if not getattr(self, "is_playing", False):
            return
        score = self._get_score()
        if not score:
            self.is_playing = False
            return

        elapsed = time.monotonic() - self.start_time
        w = self.world()
        sr = 22050

        # Prune expired active key highlights
        spans = getattr(self, "_active_spans", [])
        alive_spans = [sp for sp in spans if sp[0] > elapsed]
        changed_keys = len(alive_spans) != len(spans)
        self._active_spans = alive_spans

        if self.event_cursor < len(score) and score[self.event_cursor][0] <= elapsed:
            batch_t0 = score[self.event_cursor][0]
            batch_events = []
            prev_t = batch_t0
            while self.event_cursor < len(score):
                ev = score[self.event_cursor]
                ev_t = ev[0]
                if not batch_events:
                    batch_events.append(ev)
                    prev_t = ev_t
                    self.event_cursor += 1
                elif ev_t <= elapsed or (ev_t - prev_t <= 0.18 and ev_t - batch_t0 <= 0.65):
                    batch_events.append(ev)
                    prev_t = ev_t
                    self.event_cursor += 1
                else:
                    break

            if len(batch_events) == 1:
                ev_t, ev_dur, nv_pairs, _sec = batch_events[0]
                batch_snd = self._synth_chord(nv_pairs, ev_dur)
                for n_name, vel in nv_pairs:
                    self._active_spans.append((ev_t + ev_dur, _note_name_to_midi(n_name), float(vel)))
            else:
                batch_buf = array.array("h")
                for ev_t, ev_dur, nv_pairs, _sec in batch_events:
                    ev_snd = self._synth_chord(nv_pairs, ev_dur)
                    ev_samples = ev_snd.samples
                    offset_idx = max(0, int(round((ev_t - batch_t0) * sr)))
                    cur_len = len(batch_buf)
                    if offset_idx >= cur_len:
                        if offset_idx > cur_len:
                            batch_buf.extend(array.array("h", [0] * (offset_idx - cur_len)))
                        batch_buf.extend(ev_samples)
                    else:
                        end_idx = offset_idx + len(ev_samples)
                        if end_idx > cur_len:
                            batch_buf.extend(array.array("h", [0] * (end_idx - cur_len)))
                        overlap_end = min(cur_len, end_idx)
                        for j in range(overlap_end - offset_idx):
                            idx = offset_idx + j
                            batch_buf[idx] = max(-32767, min(32767, batch_buf[idx] + ev_samples[j]))
                        if end_idx > cur_len:
                            tail_start = cur_len - offset_idx
                            batch_buf[cur_len:end_idx] = ev_samples[tail_start:]
                    for n_name, vel in nv_pairs:
                        self._active_spans.append((ev_t + ev_dur, _note_name_to_midi(n_name), float(vel)))
                batch_snd = SampledSound(batch_buf, sample_rate=sr, channels=1)

            if w is not None and hasattr(w, "play_sound"):
                w.play_sound(batch_snd)
            changed_keys = True

        # Rebuild active_notes dict {midi_num: max_velocity}
        new_active: Dict[int, float] = {}
        for _end_t, m_num, vel in self._active_spans:
            if m_num not in new_active or vel > new_active[m_num]:
                new_active[m_num] = vel
        self.active_notes = new_active

        if self.event_cursor >= len(score):
            last_t, last_dur, _, _ = score[-1]
            if elapsed >= last_t + last_dur:
                self.is_playing = False
                self.active_notes = {}
                self._active_spans = []
                self.current_status = "Finished (Click to Replay)"
                self.changed()
                return

        if changed_keys:
            self.changed()

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        if button == 0:
            self._down_pos = (px, py)

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        if button == 0 and getattr(self, "_down_pos", None) is not None:
            dx = px - self._down_pos[0]
            dy = py - self._down_pos[1]
            self._down_pos = None
            if (dx * dx + dy * dy) <= 36.0:
                self.toggle_play()

    # --- 88-Key Piano Keyboard Rendering ---

    def _active_key_color(self, vel: float, is_black: bool) -> str:
        if vel >= 0.78:
            return "#f0c674" if is_black else "#ebcb8b"
        if vel >= 0.50:
            return "#d08770" if is_black else "#e5c07b"
        return "#a3be8c" if is_black else "#b5cea8"

    def draw_on(self, canvas: DisplayCanvas) -> None:
        canvas.fill_round_rect(
            self.x, self.y, self.width, self.height, self.corner_radius,
            self.color, self.border_color, self.border_width,
        )

        # Header
        canvas.fill_round_rect(self.x + 6, self.y + 6, self.width - 12, 26, 5.0, "#14171d", "#3b4252", 1.0)
        src_label = (
            self.source_ref.display_name()
            if self.source_ref is not None and hasattr(self.source_ref, "display_name")
            else "No MIDI stream"
        )
        canvas.draw_text(f"MIDI Player — {src_label}", self.x + 14, self.y + 23, color="#ebcb8b", font="bold 12px sans-serif")

        # 88-key piano keyboard: MIDI 21 (A0) .. 108 (C8), 52 white keys
        kb_x = self.x + 12.0
        kb_y = self.y + 38.0
        kb_w = self.width - 24.0
        kb_h = max(64.0, self.height - 78.0)
        canvas.fill_rect(kb_x - 2, kb_y - 2, kb_w + 4, kb_h + 4, "#111318")

        active = getattr(self, "active_notes", {}) or {}
        white_midis = [m for m in range(21, 109) if (m % 12) not in _BLACK_PCS]
        num_whites = len(white_midis)  # 52
        kw = kb_w / float(num_whites)
        white_x_by_midi: Dict[int, float] = {}

        # Draw white keys first
        for idx, m in enumerate(white_midis):
            kx = kb_x + idx * kw
            white_x_by_midi[m] = kx
            vel = active.get(m)
            fill = self._active_key_color(vel, is_black=False) if vel is not None else "#eceff4"
            canvas.fill_rect(kx + 0.3, kb_y, max(2.0, kw - 0.6), kb_h, fill)
            canvas.stroke_rect(kx + 0.3, kb_y, max(2.0, kw - 0.6), kb_h, "#2e3440", 0.6)

        # Draw black keys on top
        bw_key = max(3.0, kw * 0.62)
        bh_key = kb_h * 0.60
        for m in range(21, 109):
            if (m % 12) in _BLACK_PCS:
                left_white_x = white_x_by_midi.get(m - 1)
                if left_white_x is None:
                    continue
                bx = left_white_x + kw - bw_key * 0.5
                vel = active.get(m)
                fill = self._active_key_color(vel, is_black=True) if vel is not None else "#1b1f27"
                canvas.fill_rect(bx, kb_y, bw_key, bh_key, fill)
                canvas.stroke_rect(bx, kb_y, bw_key, bh_key, "#0f1115", 0.6)

        # Progress bar & footer status
        score = self._get_score()
        total = max(1, len(score))
        prog = min(1.0, getattr(self, "event_cursor", 0) / float(total))
        bar_y = self.y + self.height - 30.0
        canvas.fill_round_rect(self.x + 12, bar_y, self.width - 24, 5, 2.5, "#14171d", "#4c566a", 0.7)
        if prog > 0:
            canvas.fill_round_rect(self.x + 12, bar_y, max(5.0, (self.width - 24) * prog), 5, 2.5, "#d4af37", "", 0.0)

        status_txt = getattr(self, "current_status", "Connect a .mid FileMorph")
        badge = "PLAYING — Click to Stop" if self.is_playing else "STOPPED — Click to Play"
        canvas.draw_text(status_txt, self.x + 12, self.y + self.height - 9, color="#d8dee9", font="11px sans-serif")
        bw = canvas.measure_text(badge, "bold 11px sans-serif")
        canvas.draw_text(badge, self.x + self.width - bw - 12, self.y + self.height - 9, color="#a3be8c" if self.is_playing else "#88c0d0", font="bold 11px sans-serif")

        # Left input port dot
        ix, iy = self.input_port_center()
        canvas.fill_circle(ix, iy, 6.0, "#88c0d0", "#14171d", 1.5)
