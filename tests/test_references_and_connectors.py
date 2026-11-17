import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from objectpond.kernel.image import ImageSerializer
from objectpond.kernel.object_memory import SystemDictionary
from objectpond.kernel.references import FileReference, UrlReference
from objectpond.morphic.canvas import DisplayCanvas, RecordingBackend
from objectpond.morphic.software_canvas import SoftwareCanvasBackend
from objectpond.morphic.connectors import ConnectionArrowMorph, FileMorph, UrlMorph
from objectpond.morphic.hex_editor import HexEditorMorph
from objectpond.morphic.markdown_editor import MarkdownEditorMorph
from objectpond.morphic.midi_player import MidiPlayerMorph
from objectpond.morphic.midi import parse_midi_bytes
from objectpond.morphic.morph import Morph
from objectpond.morphic.world import WorldMorph
from server import ObjectPondHandler


class _DummyMidiReceiver(Morph):
    def __init__(self, x=300, y=100, width=160, height=120):
        super().__init__(x, y, width, height)
        self.received_events = []
        self.disconnected = False

    def accepts_stream(self, source):
        return True

    def connect_stream(self, ref):
        data = ref.open_stream().read()
        self.received_events = parse_midi_bytes(data)

    def disconnect_stream(self, ref):
        self.disconnected = True


class TestReferencesAndConnectors(unittest.TestCase):
    def test_file_reference_transient_cache_and_image_roundtrip(self):
        st = SystemDictionary()
        world = WorldMorph(800, 600, smalltalk=st)
        ref = FileReference("assets", "bwv565.mid")
        raw_midi = ref.read_bytes()
        self.assertTrue(raw_midi.startswith(b"MThd"))
        self.assertIsNotNone(ref._cached_bytes)

        fm = FileMorph(reference=ref, x=60, y=100)
        world.add_morph(fm)

        ser = ImageSerializer(st)
        snap = ser.create_snapshot_dict(world)
        ref_records = [o for o in snap["objects"] if o.get("class") == "FileReference"]
        self.assertEqual(len(ref_records), 1)
        self.assertNotIn("_cached_bytes", ref_records[0]["state"])

        img_bytes = ser.save_image_bytes(world)
        restored = ser.load_image_bytes(img_bytes)
        restored_fm = [m for m in restored.submorphs if isinstance(m, FileMorph)][0]
        self.assertFalse(hasattr(restored_fm.reference, "_cached_bytes"))
        self.assertEqual(restored_fm.read_bytes(), raw_midi)

    def test_parse_midi_bytes_bwv565(self):
        ref = FileReference("assets", "bwv565.mid")
        events = parse_midi_bytes(ref.read_bytes())
        self.assertEqual(len(events), 2842)
        self.assertEqual(events[0], (0.0, 0.075, ["A4", "A5"], "Toccata: Opening"))
        self.assertEqual(events[1], (0.075, 0.075, ["G4", "G5"], "Toccata: Opening"))
        self.assertEqual(events[2], (0.15, 0.8, ["A4", "A5"], "Toccata: Opening"))
        total_dur = events[-1][0] + events[-1][1]
        self.assertAlmostEqual(total_dur, 572.0, places=1)

    def test_port_drag_creates_connection_arrow_and_streams_data(self):
        st = SystemDictionary()
        world = WorldMorph(800, 600, smalltalk=st)
        fm = FileMorph(anchor="assets", path="bwv565.mid", x=50, y=100)
        rx = _DummyMidiReceiver(x=280, y=90)
        world.add_morph(fm)
        world.add_morph(rx)

        px, py = fm.output_port_center()
        self.assertTrue(fm.wants_mouse_drag(px, py))
        world.handle_mouse_down(px, py, 0)
        self.assertIs(world._connecting_source, fm)
        world.handle_mouse_move(rx.x + 40, rx.y + 40)
        world.handle_mouse_up(rx.x + 40, rx.y + 40, 0)

        self.assertIsNone(world._connecting_source)
        self.assertEqual(len(world.connections), 1)
        self.assertIsInstance(world.connections[0], ConnectionArrowMorph)
        self.assertEqual(len(rx.received_events), 2842)

        # Render full world with arrow & icon
        canvas = DisplayCanvas(SoftwareCanvasBackend(800, 600))
        world.full_draw_on(canvas)

        # Click midpoint 'x' to disconnect
        mx, my = world.connections[0].midpoint()
        world.handle_mouse_down(mx, my, 0)
        self.assertEqual(len(world.connections), 0)
        self.assertTrue(rx.disconnected)

    def test_server_fs_read_endpoint_and_traversal_guard(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), ObjectPondHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/fs/read?anchor=assets&path=bwv565.mid") as resp:
                self.assertEqual(resp.status, 200)
                data = resp.read()
                self.assertTrue(data.startswith(b"MThd"))

            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/fs/read?anchor=assets&path=../server.py")
            self.assertEqual(ctx.exception.code, 403)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_hex_editor_stream_passthrough_and_live_edit(self):
        st = SystemDictionary()
        world = WorldMorph(800, 600, smalltalk=st)
        fm = FileMorph(anchor="assets", path="bwv565.mid", x=20, y=80)
        hx = HexEditorMorph(x=160, y=60, width=548, height=280)
        rx = _DummyMidiReceiver(x=740, y=90)
        world.add_morph(fm)
        world.add_morph(hx)
        world.add_morph(rx)

        # Wire FileMorph -> HexEditorMorph -> _DummyMidiReceiver
        world.connect_morphs(fm, hx)
        ox, oy = hx.output_port_center()
        self.assertTrue(hx.wants_mouse_drag(ox, oy))
        world.connect_morphs(hx, rx)
        self.assertEqual(len(rx.received_events), 2842)

        # Edit a non-header byte (e.g. offset 22) via keyboard nibbles '7', 'F' -> 0x7F
        hx.selected_offset = 22
        hx.on_key_down("7")
        hx.on_key_down("f")
        self.assertTrue(hx.dirty)
        self.assertEqual(hx.read_bytes()[22], 0x7F)
        self.assertEqual(hx.selected_offset, 23)

        # Draw & image round-trip preserves edited buffer without storing _buffer
        canvas = DisplayCanvas(SoftwareCanvasBackend(800, 600))
        world.full_draw_on(canvas)
        ser = ImageSerializer(st)
        snap = ser.create_snapshot_dict(world)
        hx_rec = [o for o in snap["objects"] if o.get("class") == "HexEditorMorph"][0]
        self.assertNotIn("_buffer", hx_rec["state"])
        restored = ser.load_image_bytes(ser.save_image_bytes(world))
        restored_hx = [m for m in restored.submorphs if isinstance(m, HexEditorMorph)][0]
        self.assertEqual(restored_hx.read_bytes()[22], 0x7F)

    def test_draw_error_in_one_morph_does_not_hide_subsequent_morphs(self):
        class BrokenDrawMorph(Morph):
            def draw_on(self, canvas):
                raise RuntimeError("boom in draw")

        st = SystemDictionary()
        world = WorldMorph(800, 600, smalltalk=st)
        broken = BrokenDrawMorph(10, 10, 80, 40)
        fm = FileMorph(anchor="assets", path="bwv565.mid", x=200, y=100)
        world.add_morph(broken)
        world.add_morph(fm)

        # Clicking FileMorph brings it to front (after broken); full_draw_on must still render it
        world.handle_mouse_down(fm.x + 20, fm.y + 20, 0)
        world.handle_mouse_up(fm.x + 20, fm.y + 20, 0)
        canvas = DisplayCanvas(RecordingBackend())
        world.full_draw_on(canvas)
        self.assertIn("bwv565.mid", str(canvas.backend.commands))

    def test_midi_player_velocity_and_88_key_keyboard(self):
        import struct

        # Build a minimal 1-track MIDI with a soft note (vel=25) and a loud note (vel=120)
        def vlq(n):
            out = [n & 0x7F]
            n >>= 7
            while n:
                out.append((n & 0x7F) | 0x80)
                n >>= 7
            return bytes(reversed(out))

        trk = bytearray()
        trk += vlq(0) + bytes([0x90, 60, 25])    # C4 soft
        trk += vlq(240) + bytes([0x80, 60, 0])
        trk += vlq(0) + bytes([0x90, 64, 120])   # E4 loud
        trk += vlq(240) + bytes([0x80, 64, 0])
        trk += vlq(0) + bytes([0xFF, 0x2F, 0x00])
        midi_bytes = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(trk)) + bytes(trk)

        events = parse_midi_bytes(midi_bytes, include_velocity=True)
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[0][2][0][1], 25 / 127.0, places=2)
        self.assertAlmostEqual(events[1][2][0][1], 120 / 127.0, places=2)

        st = SystemDictionary()
        world = WorldMorph(900, 600, smalltalk=st)
        player = MidiPlayerMorph(x=100, y=200)
        world.add_morph(player)

        # Velocity scales synthesized PCM peak amplitude
        soft_snd = player._synth_chord([("C4", 25 / 127.0)], 0.1)
        loud_snd = player._synth_chord([("C4", 120 / 127.0)], 0.1)
        self.assertGreater(max(abs(s) for s in loud_snd.samples), max(abs(s) for s in soft_snd.samples) * 2)

        # Render 88-key keyboard with active note highlighted and no Toccata title
        player.active_notes = {60: 0.9}
        canvas = DisplayCanvas(RecordingBackend())
        player.draw_on(canvas)
        cmd_str = str(canvas.backend.commands)
        self.assertIn("MIDI Player", cmd_str)
        self.assertNotIn("Toccata", cmd_str)
        # 52 white keys + 36 black keys = 88 key rects (plus background/frame rects)
        rect_count = sum(1 for c in canvas.backend.commands if c[0] == "fill_rect")
        self.assertGreaterEqual(rect_count, 88)

    def test_markdown_editor_stream_connection_edit_preview_and_save(self):
        import uuid
        from pathlib import Path

        assets_dir = FileReference.ANCHORS["assets"]
        fname = f"_test_note_{uuid.uuid4().hex[:8]}.md"
        fpath = assets_dir / fname
        initial_md = "# Hello Pond\n\nSome **bold** and `code` with [link](https://example.com).\n\n- Item A\n> Quoted\n\n```python\nx = 1\n```\n"
        fpath.write_text(initial_md, encoding="utf-8")
        try:
            st = SystemDictionary()
            world = WorldMorph(1000, 700, smalltalk=st)

            fm = FileMorph(anchor="assets", path=fname, x=20, y=100)
            md = MarkdownEditorMorph(x=200, y=80, width=620, height=380)
            downstream = HexEditorMorph(x=840, y=80, width=140, height=200)
            world.add_morph(fm)
            world.add_morph(md)
            world.add_morph(downstream)

            # Port-drag FileMorph -> MarkdownEditorMorph
            ox, oy = fm.output_port_center()
            world.handle_mouse_down(ox, oy, 0)
            world.handle_mouse_move(md.x + 120, md.y + 120)
            world.handle_mouse_up(md.x + 120, md.y + 120, 0)

            self.assertEqual(len(world.connections), 1)
            self.assertEqual(md.editor.text, initial_md)
            self.assertFalse(md.dirty)

            # Connect MarkdownEditorMorph -> HexEditorMorph
            world.connect_morphs(md, downstream)
            self.assertEqual(downstream.read_bytes().decode("utf-8"), initial_md)

            # Edit via key event and verify dirty, downstream passthrough, and preview rendering
            md.on_key_down("!")
            self.assertTrue(md.dirty)
            self.assertTrue(downstream.read_bytes().decode("utf-8").startswith("!"))

            canvas = DisplayCanvas(RecordingBackend())
            world.full_draw_on(canvas)
            cmd_str = str(canvas.backend.commands)
            self.assertIn("Hello Pond", cmd_str)
            self.assertIn("Item A", cmd_str)
            self.assertIn("x = 1", cmd_str)

            # Mode switching & Revert
            md.set_mode("preview")
            self.assertFalse(md.editor.visible)
            md.set_mode("edit")
            self.assertTrue(md.editor.visible)
            md.set_mode("split")

            md.revert()
            self.assertFalse(md.dirty)
            self.assertEqual(md.editor.text, initial_md)

            # Edit and Save back to disk
            md.editor.text = "# Saved Title\n"
            md.save()
            self.assertFalse(md.dirty)
            self.assertEqual(Path(fpath).read_text(encoding="utf-8"), "# Saved Title\n")

            # Image snapshot roundtrip
            ser = ImageSerializer(st)
            restored = ser.load_image_bytes(ser.save_image_bytes(world))
            restored_md = [m for m in restored.submorphs if isinstance(m, MarkdownEditorMorph)][0]
            self.assertEqual(restored_md.editor.text, "# Saved Title\n")
            self.assertEqual(len(restored.connections), 2)
        finally:
            if fpath.exists():
                fpath.unlink()

    def test_server_fs_write_endpoint_and_traversal_guard(self):
        import json
        import uuid

        assets_dir = FileReference.ANCHORS["assets"]
        fname = f"_test_write_{uuid.uuid4().hex[:8]}.md"
        fpath = assets_dir / fname

        server = ThreadingHTTPServer(("127.0.0.1", 0), ObjectPondHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/fs/write?anchor=assets&path={fname}",
                data=b"# Written via API\n",
                method="POST",
                headers={"Content-Type": "application/octet-stream"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                payload = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(payload["status"], "ok")
            self.assertEqual(fpath.read_bytes(), b"# Written via API\n")

            bad_req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/fs/write?anchor=assets&path=../evil.md",
                data=b"nope",
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(bad_req, timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            if fpath.exists():
                fpath.unlink()


if __name__ == "__main__":
    unittest.main()
