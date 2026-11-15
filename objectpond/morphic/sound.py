import array
import base64
import io
import math
import random
import wave
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


_NOTE_OFFSETS = {
    "C": 0, "C#": 1, "DB": 1,
    "D": 2, "D#": 3, "EB": 3,
    "E": 4,
    "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8,
    "A": 9, "A#": 10, "BB": 10,
    "B": 11,
}


def note_to_hz(note: Union[str, int, float]) -> float:
    """Converts a note name ('A4', 'C#5'), MIDI number (69), or frequency to Hz."""
    if isinstance(note, (int, float)):
        if note <= 127:
            return 440.0 * (2.0 ** ((float(note) - 69.0) / 12.0))
        return float(note)
    s = str(note).strip().upper()
    if len(s) >= 2 and s[1] in ("#", "B"):
        name, oct_str = s[:2], s[2:]
    else:
        name, oct_str = s[:1], s[1:]
    octave = int(oct_str)
    midi = (octave + 1) * 12 + _NOTE_OFFSETS[name]
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


class ADSR:
    """Linear ADSR amplitude envelope."""

    def __init__(
        self,
        attack: float = 0.01,
        decay: float = 0.08,
        sustain: float = 0.7,
        release: float = 0.12,
    ):
        self.attack = max(0.0, float(attack))
        self.decay = max(0.0, float(decay))
        self.sustain = max(0.0, min(1.0, float(sustain)))
        self.release = max(0.0, float(release))

    def gain_at(self, t: float, total_duration: float) -> float:
        if t < 0.0 or t > total_duration:
            return 0.0
        rel_start = max(0.0, total_duration - self.release)
        if self.release > 0.0 and t >= rel_start:
            base = self._adr_level(rel_start)
            frac = max(0.0, 1.0 - (t - rel_start) / self.release)
            return base * frac
        return self._adr_level(t)

    def _adr_level(self, t: float) -> float:
        if self.attack > 0.0 and t < self.attack:
            return t / self.attack
        t_dec = t - self.attack
        if self.decay > 0.0 and t_dec < self.decay:
            return 1.0 - (1.0 - self.sustain) * (t_dec / self.decay)
        return self.sustain


class SampledSound:
    """
    First-class audio object holding a 16-bit signed PCM binary payload (`array.array('h')`).
    Persists in ObjectPond .image snapshots via zlib+base64 just like Form bitmaps.
    """

    def __init__(
        self,
        samples: Optional[Union[array.array, Sequence[int]]] = None,
        sample_rate: int = 44100,
        channels: int = 1,
    ):
        self.sample_rate = max(8000, int(sample_rate))
        self.channels = max(1, int(channels))
        if isinstance(samples, array.array) and samples.typecode == "h":
            self.samples = samples
        elif samples is not None:
            self.samples = array.array("h", (max(-32767, min(32767, int(v))) for v in samples))
        else:
            self.samples = array.array("h")

    def duration(self) -> float:
        frames = len(self.samples) // self.channels
        return frames / float(self.sample_rate)

    def to_bytes(self) -> bytes:
        return self.samples.tobytes()

    @classmethod
    def from_bytes(cls, raw: bytes, sample_rate: int = 44100, channels: int = 1) -> "SampledSound":
        arr = array.array("h")
        arr.frombytes(raw)
        return cls(samples=arr, sample_rate=sample_rate, channels=channels)

    def to_wav_bytes(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.samples.tobytes())
        return buf.getvalue()

    def to_pcm_b64(self) -> str:
        return base64.b64encode(self.samples.tobytes()).decode("ascii")

    def gain(self, factor: float) -> "SampledSound":
        f = float(factor)
        out = array.array("h", (max(-32767, min(32767, int(s * f))) for s in self.samples))
        return SampledSound(out, self.sample_rate, self.channels)

    def append(self, other: "SampledSound") -> "SampledSound":
        out = array.array("h", self.samples)
        out.extend(other.samples)
        return SampledSound(out, self.sample_rate, self.channels)

    def mix(self, other: "SampledSound", offset_sec: float = 0.0) -> "SampledSound":
        offset_idx = max(0, int(round(offset_sec * self.sample_rate)) * self.channels)
        total_len = max(len(self.samples), offset_idx + len(other.samples))
        out = array.array("h", [0] * total_len)
        for i, v in enumerate(self.samples):
            out[i] = v
        for j, v in enumerate(other.samples):
            idx = offset_idx + j
            out[idx] = max(-32767, min(32767, out[idx] + v))
        return SampledSound(out, self.sample_rate, self.channels)

    def slice(self, start_sec: float, end_sec: float) -> "SampledSound":
        i0 = max(0, int(round(start_sec * self.sample_rate)) * self.channels)
        i1 = min(len(self.samples), int(round(end_sec * self.sample_rate)) * self.channels)
        return SampledSound(self.samples[i0:i1], self.sample_rate, self.channels)

    def lowpass(self, cutoff_hz: float = 1200.0) -> "SampledSound":
        if not self.samples:
            return SampledSound(self.samples, self.sample_rate, self.channels)
        rc = 1.0 / (2.0 * math.pi * max(20.0, float(cutoff_hz)))
        dt = 1.0 / float(self.sample_rate)
        alpha = dt / (rc + dt)
        out = array.array("h", [0] * len(self.samples))
        prev = float(self.samples[0])
        out[0] = int(prev)
        for i in range(1, len(self.samples)):
            prev = prev + alpha * (float(self.samples[i]) - prev)
            out[i] = max(-32767, min(32767, int(prev)))
        return SampledSound(out, self.sample_rate, self.channels)

    def echo(self, delay_sec: float = 0.18, decay: float = 0.4) -> "SampledSound":
        delay_samples = max(1, int(round(delay_sec * self.sample_rate)) * self.channels)
        out = array.array("h", self.samples)
        for i in range(delay_samples, len(out)):
            mixed = out[i] + int(out[i - delay_samples] * decay)
            out[i] = max(-32767, min(32767, mixed))
        return SampledSound(out, self.sample_rate, self.channels)

    def play(self, world: Optional[Any] = None) -> bool:
        if world is not None and hasattr(world, "play_sound"):
            return world.play_sound(self)
        return False


class SoundSynth:
    """Pure-Python waveform, additive, FM, and sequence synthesizer."""

    @staticmethod
    def _sample_wave(wave_type: str, phase: float) -> float:
        p = phase % 1.0
        if wave_type == "sine":
            return math.sin(2.0 * math.pi * p)
        if wave_type == "square":
            return 1.0 if p < 0.5 else -1.0
        if wave_type in ("saw", "sawtooth"):
            return 2.0 * p - 1.0
        if wave_type == "triangle":
            return 4.0 * p if p < 0.25 else (2.0 - 4.0 * p if p < 0.75 else 4.0 * p - 4.0)
        if wave_type == "noise":
            return random.uniform(-1.0, 1.0)
        return math.sin(2.0 * math.pi * p)

    @classmethod
    def oscillator(
        cls,
        wave: str = "sine",
        freq: Union[float, str] = 440.0,
        duration: float = 0.5,
        amp: float = 0.5,
        env: Optional[ADSR] = None,
        sample_rate: int = 44100,
    ) -> SampledSound:
        hz = note_to_hz(freq)
        dur = max(0.01, float(duration))
        n = int(round(dur * sample_rate))
        envelope = env or ADSR()
        out = array.array("h", [0] * n)
        for i in range(n):
            t = i / float(sample_rate)
            g = envelope.gain_at(t, dur)
            val = cls._sample_wave(wave, hz * t) * amp * g
            out[i] = max(-32767, min(32767, int(val * 32767.0)))
        return SampledSound(out, sample_rate=sample_rate, channels=1)

    @classmethod
    def additive(
        cls,
        partials: Sequence[Tuple[float, float]] = ((1.0, 1.0), (2.0, 0.5), (3.0, 0.25)),
        base_freq: Union[float, str] = 440.0,
        duration: float = 0.6,
        amp: float = 0.5,
        env: Optional[ADSR] = None,
        sample_rate: int = 44100,
    ) -> SampledSound:
        hz = note_to_hz(base_freq)
        dur = max(0.01, float(duration))
        n = int(round(dur * sample_rate))
        envelope = env or ADSR()
        norm = max(1e-6, sum(abs(w) for _m, w in partials))
        out = array.array("h", [0] * n)
        for i in range(n):
            t = i / float(sample_rate)
            s = sum(w * math.sin(2.0 * math.pi * hz * mult * t) for mult, w in partials) / norm
            val = s * amp * envelope.gain_at(t, dur)
            out[i] = max(-32767, min(32767, int(val * 32767.0)))
        return SampledSound(out, sample_rate=sample_rate, channels=1)

    @classmethod
    def fm(
        cls,
        carrier_freq: Union[float, str] = 440.0,
        mod_freq: Union[float, str] = 220.0,
        mod_index: float = 3.0,
        duration: float = 0.7,
        amp: float = 0.5,
        env: Optional[ADSR] = None,
        sample_rate: int = 44100,
    ) -> SampledSound:
        fc = note_to_hz(carrier_freq)
        fm_hz = note_to_hz(mod_freq)
        dur = max(0.01, float(duration))
        n = int(round(dur * sample_rate))
        envelope = env or ADSR(0.005, 0.15, 0.4, 0.25)
        out = array.array("h", [0] * n)
        for i in range(n):
            t = i / float(sample_rate)
            mod = mod_index * math.sin(2.0 * math.pi * fm_hz * t)
            s = math.sin(2.0 * math.pi * fc * t + mod)
            val = s * amp * envelope.gain_at(t, dur)
            out[i] = max(-32767, min(32767, int(val * 32767.0)))
        return SampledSound(out, sample_rate=sample_rate, channels=1)

    @classmethod
    def sequence(
        cls,
        events: Sequence[Tuple[float, "SampledSound"]],
        sample_rate: int = 44100,
    ) -> SampledSound:
        """Mixes a list of (offset_sec, SampledSound) events into one SampledSound."""
        acc = SampledSound(sample_rate=sample_rate)
        for offset_sec, snd in events:
            acc = acc.mix(snd, offset_sec=offset_sec)
        return acc
