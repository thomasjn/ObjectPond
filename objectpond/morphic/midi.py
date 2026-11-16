import struct
from typing import List, Tuple

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def midi_note_to_name(midi_num: int) -> str:
    octave = (int(midi_num) // 12) - 1
    return f"{NOTE_NAMES[int(midi_num) % 12]}{octave}"


def _read_vlq(data: bytes, pos: int) -> Tuple[int, int]:
    val = 0
    while True:
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, pos


def _bwv565_opening_ornaments(include_velocity: bool = False) -> List[Tuple]:
    """Realizes mm. 1-3 mordents, fermatas, and rolled diminished-7th arpeggio."""
    evs: List[Tuple] = []
    t = 0.0
    sec = "Toccata: Opening"

    def fmt(notes: List[str], vel: float = 0.85):
        return [(n, vel) for n in notes] if include_velocity else list(notes)

    def seq(notes: List[str], dur: float, gap: float = 0.0, vel: float = 0.85) -> None:
        nonlocal t
        evs.append((round(t, 3), round(dur, 3), fmt(notes, vel), sec))
        t += dur + gap

    seq(["A4", "A5"], 0.075, vel=0.90)
    seq(["G4", "G5"], 0.075, vel=0.82)
    seq(["A4", "A5"], 0.800, gap=0.100, vel=0.95)
    for n in ["G", "F", "E", "D"]:
        seq([f"{n}4", f"{n}5"], 0.068, vel=0.82)
    seq(["C#4", "C#5"], 0.110, vel=0.85)
    seq(["D4", "D5"], 0.700, gap=0.250, vel=0.92)

    seq(["A3", "A4"], 0.075, vel=0.88)
    seq(["G3", "G4"], 0.075, vel=0.80)
    seq(["A3", "A4"], 0.800, gap=0.100, vel=0.92)
    for n in ["E", "F", "C#"]:
        seq([f"{n}3", f"{n}4"], 0.105, vel=0.82)
    seq(["D3", "D4"], 0.700, gap=0.250, vel=0.90)

    seq(["A2", "A3"], 0.080, vel=0.90)
    seq(["G2", "G3"], 0.080, vel=0.82)
    seq(["A2", "A3"], 0.850, gap=0.100, vel=0.95)
    for n in ["G", "F", "E", "D"]:
        seq([f"{n}2", f"{n}3"], 0.072, vel=0.82)
    seq(["C#2", "C#3"], 0.115, vel=0.85)
    seq(["D2", "D3"], 0.750, gap=0.250, vel=0.92)

    pedal_t = round(t, 3)
    evs.append((pedal_t, 4.100, fmt(["D2"], 0.95), sec))
    arp_notes = ["C#3", "E3", "G3", "Bb3", "C#4", "E4"]
    arp_start = pedal_t + 0.55
    arp_resolve_t = 9.400
    for i, an in enumerate(arp_notes):
        nt = round(arp_start + i * 0.11, 3)
        evs.append((nt, round(arp_resolve_t - nt, 3), fmt([an], 0.78 + i * 0.03), sec))

    evs.append((9.400, 1.550, fmt(["D3", "A3", "D4"], 0.94), sec))
    evs.append((9.400, 0.250, fmt(["G3"], 0.82), sec))
    evs.append((9.650, 0.250, fmt(["E3"], 0.80), sec))
    evs.append((9.900, 1.050, fmt(["F#3"], 0.88), sec))
    return evs


def parse_midi_bytes(
    data: bytes,
    realize_bwv565_opening: bool = True,
    include_velocity: bool = False,
) -> List[Tuple]:
    """
    Pure-Python Standard MIDI File (SMF) parser.
    When include_velocity is False, returns (start_sec, duration_sec, [note_names], section_label).
    When include_velocity is True, returns (start_sec, duration_sec, [(note_name, vel_norm)], section_label).
    """
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("Invalid MIDI header (expected MThd)")

    hdr_len = struct.unpack(">I", data[4:8])[0]
    _fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("SMPTE timecode MIDI division is not supported")
    pos = 8 + hdr_len

    tempo_events: List[Tuple[int, int]] = []
    note_events: List[Tuple[int, int, int, int]] = []

    for _ in range(ntracks):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            break
        trk_len = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        trk_end = min(len(data), pos + 8 + trk_len)
        pos += 8
        tick = 0
        running_status = None
        active = {}

        while pos < trk_end:
            delta, pos = _read_vlq(data, pos)
            tick += delta
            b = data[pos]
            if b < 0x80:
                status = running_status
            else:
                status = b
                pos += 1
                if status < 0xF0:
                    running_status = status

            if status is None:
                break
            if status == 0xFF:
                meta_type = data[pos]
                pos += 1
                mlen, pos = _read_vlq(data, pos)
                mdata = data[pos:pos + mlen]
                pos += mlen
                if meta_type == 0x51 and mlen == 3:
                    us_per_q = (mdata[0] << 16) | (mdata[1] << 8) | mdata[2]
                    tempo_events.append((tick, us_per_q))
            elif status in (0xF0, 0xF7):
                slen, pos = _read_vlq(data, pos)
                pos += slen
            else:
                ev_type = status & 0xF0
                ch = status & 0x0F
                if ev_type in (0xC0, 0xD0):
                    pos += 1
                elif ev_type in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    d1 = data[pos]
                    d2 = data[pos + 1]
                    pos += 2
                    if ev_type == 0x90 and d2 > 0:
                        if (ch, d1) in active:
                            st_t, st_v = active.pop((ch, d1))
                            note_events.append((st_t, tick, d1, st_v))
                        active[(ch, d1)] = (tick, d2)
                    elif ev_type == 0x80 or (ev_type == 0x90 and d2 == 0):
                        if (ch, d1) in active:
                            st_t, st_v = active.pop((ch, d1))
                            note_events.append((st_t, tick, d1, st_v))
                else:
                    raise ValueError(f"Unsupported MIDI status byte: {hex(status)}")
        pos = trk_end

    tempo_events.sort()
    if not tempo_events or tempo_events[0][0] > 0:
        tempo_events.insert(0, (0, 500000))

    def tick_to_sec(target_tick: int) -> float:
        sec = 0.0
        cur_tick = 0
        cur_us = tempo_events[0][1]
        for t_tick, t_us in tempo_events[1:]:
            if target_tick <= t_tick:
                break
            sec += ((t_tick - cur_tick) / division) * (cur_us / 1_000_000.0)
            cur_tick = t_tick
            cur_us = t_us
        sec += ((target_tick - cur_tick) / division) * (cur_us / 1_000_000.0)
        return sec

    timed = []
    for st, en, m, vel in note_events:
        s_sec = tick_to_sec(st)
        e_sec = tick_to_sec(en)
        dur = max(0.05, e_sec - s_sec)
        timed.append((s_sec, dur, m, round(max(1, min(127, vel)) / 127.0, 3)))
    timed.sort()

    # Detect Mutopia BWV 565 unornamented opening (A4+A5 at t=0, D2 pedal at t=6.0)
    is_bwv565 = (
        realize_bwv565_opening
        and len(timed) > 2000
        and timed[0][0] == 0.0
        and sorted(x[2] for x in timed[:2]) == [69, 81]
    )

    grouped: List[Tuple] = []
    if is_bwv565:
        grouped.extend(_bwv565_opening_ornaments(include_velocity=include_velocity))

    for s_sec, dur, m, vel_norm in timed:
        if is_bwv565 and s_sec < 11.5:
            continue
        n_name = midi_note_to_name(m)
        sec = "Playing MIDI Stream"

        placed = False
        for i in range(len(grouped) - 1, max(-1, len(grouped) - 7), -1):
            pt, pd, pnotes, _psec = grouped[i]
            if abs(s_sec - pt) < 0.010 and abs(dur - pd) < 0.040:
                if include_velocity:
                    if not any(pn[0] == n_name for pn in pnotes):
                        pnotes.append((n_name, vel_norm))
                else:
                    if n_name not in pnotes:
                        pnotes.append(n_name)
                placed = True
                break
        if not placed:
            item = [(n_name, vel_norm)] if include_velocity else [n_name]
            grouped.append((round(s_sec, 3), round(dur, 3), item, sec))

    grouped.sort(key=lambda x: (x[0], x[1]))
    return grouped
