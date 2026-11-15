import unittest
from objectpond.boot import create_default_environment
from objectpond.kernel.image import ImageSerializer
from objectpond.morphic.canvas import DisplayCanvas, RecordingBackend
from objectpond.tools.browser import SystemBrowserWindow
from objectpond.tools.workspace import WorkspaceWindow
from objectpond.tools.inspector import InspectorWindow
from objectpond.tools.transcript import TranscriptWindow, ChangesViewerWindow
from objectpond.tools.demos import BouncingAtomsMorph, BitBltPaintMorph


class TestToolsAndBootEnvironment(unittest.TestCase):
    def setUp(self):
        self.smalltalk, self.world = create_default_environment(1200, 800)
        self.backend = RecordingBackend(1200, 800)
        self.canvas = DisplayCanvas(self.backend)

    def test_default_boot_environment_and_full_draw(self):
        # Default world should have open tools and demo morphs
        self.assertGreaterEqual(len(self.world.submorphs), 3)
        # Running a full world cycle (stepping + drawing) works cleanly
        drew = self.world.do_one_cycle(self.canvas)
        self.assertTrue(drew)
        self.assertGreater(len(self.backend.commands), 20)

    def test_system_browser_live_method_editing(self):
        browser = SystemBrowserWindow(self.world, initial_class="BouncingAtomsMorph")
        self.world.add_morph(browser)
        self.assertEqual(browser.selected_class_name, "BouncingAtomsMorph")

        # Select 'step' method in browser and hot-patch it via Accept
        browser.select_method("step")
        self.assertIn("def step", browser.editor.text)

        custom_step = (
            "def step(self):\n"
            "    self.tick_count = getattr(self, 'tick_count', 0) + 1\n"
        )
        browser.editor.set_text(custom_step)
        browser.accept_editor()

        atoms = BouncingAtomsMorph(100, 100, 200, 150)
        atoms.step()
        self.assertEqual(getattr(atoms, "tick_count", 0), 1)

        # Also verify changing num_atoms from 14 to 4 in the class definition preserves
        # existing running instances' state while newly spawned instances get 4 atoms.
        running_atoms = [
            m for m in self.world.submorphs if m.__class__.__name__ == "BouncingAtomsMorph"
        ][0]
        self.assertEqual(len(running_atoms.atoms), 14)

        browser.select_method(None)
        modified_cls_src = browser.editor.text.replace("num_atoms: int = 14", "num_atoms: int = 4")
        browser.editor.set_text(modified_cls_src)
        res_cls = browser.accept_editor()
        self.assertFalse(isinstance(res_cls, Exception), f"Unexpected compile error: {res_cls}")

        # Existing running instance preserves its 14 atoms
        self.assertEqual(len(running_atoms.atoms), 14)

        # Newly spawned instance from World menu/menubar has 4 atoms
        spawned_atoms = self.world.spawn_bouncing_atoms()
        self.assertEqual(len(spawned_atoms.atoms), 4)

        # Also verify editing __init__ directly in the method pane affects new instances
        # without resetting existing instances, and syncs back into the full class definition source
        browser.select_method("__init__")
        init_src_6 = browser.editor.text.replace("num_atoms: int = 4", "num_atoms: int = 6")
        browser.editor.set_text(init_src_6)
        browser.accept_editor()
        self.assertEqual(len(running_atoms.atoms), 14)
        self.assertEqual(len(spawned_atoms.atoms), 4)
        spawned_atoms_6 = self.world.spawn_bouncing_atoms()
        self.assertEqual(len(spawned_atoms_6.atoms), 6)
        browser.select_method(None)
        self.assertIn("num_atoms: int = 6", browser.editor.text)

        browser.select_method("draw_on")
        res_method = browser.accept_editor()
        self.assertEqual(res_method, "draw_on")

        # Verify editing SystemBrowserWindow preserves the existing browser's live state
        # while newly opened SystemBrowserWindow instances use the updated title.
        browser.select_category("Tools-Browser")
        browser.select_class("SystemBrowserWindow")
        browser.select_method(None)
        old_browser_title = browser.title
        new_browser_src = browser.editor.text.replace(
            'title="System Browser"', 'title="Hot Browser"'
        )
        browser.editor.set_text(new_browser_src)
        browser.accept_editor()
        self.assertEqual(browser.title, old_browser_title)
        new_browser = self.smalltalk.get_class("SystemBrowserWindow")(self.world)
        self.assertIn("Hot Browser", new_browser.title)

        # Verify editing WorkspaceWindow.__init__ preserves the already-open WorkspaceWindow
        # while newly opened WorkspaceWindow instances get the new title.
        open_ws = [
            m for m in self.world.submorphs if m.__class__.__name__ == "WorkspaceWindow"
        ][0]
        browser.select_category("Tools-Workspace")
        browser.select_class("WorkspaceWindow")
        browser.select_method("__init__")
        new_ws_init = browser.editor.text.replace(
            'title="Workspace"', 'title="Live Scratchpad"'
        )
        browser.editor.set_text(new_ws_init)
        browser.accept_editor()
        self.assertEqual(open_ws.title, "Workspace")
        new_ws = self.smalltalk.get_class("WorkspaceWindow")(self.world)
        self.assertEqual(new_ws.title, "Live Scratchpad")

    def test_inspector_live_object_mutation(self):
        atoms = BouncingAtomsMorph(100, 100, 200, 150)
        inspector = InspectorWindow(self.world, atoms)
        self.world.add_morph(inspector)

        self.assertIn("self", inspector.field_list.items)
        inspector.eval_editor.set_text("self.color = '#ff1122'\nself.color")
        inspector.eval_editor.select_all()
        res = inspector.eval_editor.do_it()
        self.assertEqual(res, "#ff1122")
        self.assertEqual(atoms.color, "#ff1122")

        # 1. Select 'color' field and edit directly in the top-right value editor
        color_idx = inspector.field_list.items.index("color")
        inspector.field_list.select_index(color_idx)
        self.assertEqual(inspector.value_editor.text, "'#ff1122'")

        # Accept unquoted string literal for string field
        inspector.value_editor.set_text("#00ff88")
        inspector.on_accept_field_clicked()
        self.assertEqual(atoms.color, "#00ff88")
        self.assertEqual(inspector.value_editor.text, "'#00ff88'")

        # 2. Select 'width' geometry field and accept arithmetic expression via Cmd+S (accept)
        width_idx = inspector.field_list.items.index("width")
        inspector.field_list.select_index(width_idx)
        inspector.value_editor.set_text("200 + 60")
        inspector.value_editor.accept()
        self.assertEqual(atoms.width, 260)
        self.assertEqual(float(inspector.value_editor.text), 260.0)

        # 3. External mutation refreshes value_editor automatically on step()
        atoms.set_extent(310, 150)
        inspector.step()
        self.assertEqual(float(inspector.value_editor.text), 310.0)

        # 4. Inspecting a dict/list allows mutating keys/elements live
        sample_dict = {"speed": 5, "label": "atom"}
        dict_inspector = InspectorWindow(self.world, sample_dict)
        key_idx = dict_inspector.field_list.items.index("['speed']")
        dict_inspector.field_list.select_index(key_idx)
        dict_inspector.value_editor.set_text("12")
        dict_inspector.on_accept_field_clicked()
        self.assertEqual(sample_dict["speed"], 12)

    def test_workspace_transcript_changes_and_demos(self):
        ws = WorkspaceWindow(self.world)
        tr = TranscriptWindow(self.world)
        ch = ChangesViewerWindow(self.world)
        paint = BitBltPaintMorph(200, 200, 240, 180)
        self.world.add_morph(ws)
        self.world.add_morph(tr)
        self.world.add_morph(ch)
        self.world.add_morph(paint)

        # Paint on BitBltPaintMorph via World mouse down + move (should paint, NOT move the morph)
        orig_x, orig_y = paint.x, paint.y
        self.world.handle_mouse_down(orig_x + 40, orig_y + 60, 0)
        self.world.handle_mouse_move(orig_x + 80, orig_y + 90)
        self.world.handle_mouse_up(orig_x + 80, orig_y + 90, 0)
        self.assertEqual((paint.x, paint.y), (orig_x, orig_y))
        self.assertEqual(paint.bitmap.pixel_at(40 - 2, 60 - 26), paint.current_color32)
        self.assertEqual(paint.bitmap.pixel_at(80 - 2, 90 - 26), paint.current_color32)

        # Dragging on the top header bar outside swatches moves BitBltPaintMorph
        self.world.handle_mouse_down(orig_x + 220, orig_y + 12, 0)
        self.world.handle_mouse_move(orig_x + 250, orig_y + 32)
        self.world.handle_mouse_up(orig_x + 250, orig_y + 32, 0)
        self.assertEqual((paint.x, paint.y), (orig_x + 30, orig_y + 20))

        self.world.workspace_globals["Transcript"].show("Hello from test")
        self.assertIn("Hello from test", self.smalltalk.transcript_history)

        # Snapshot and restore entire booted environment with all open tools
        serializer = ImageSerializer(self.smalltalk)
        img_bytes = serializer.save_image_bytes(self.world)
        restored_world = serializer.load_image_bytes(img_bytes)
        self.assertEqual(len(restored_world.submorphs), len(self.world.submorphs))

    def test_window_resize_grip_and_halo_mouse_events_in_enlarged_area(self):
        browser = self.world.submorphs[0]
        self.assertIsInstance(browser, SystemBrowserWindow)

        # 1. Resize via bottom-right 16x16 resize grip (which overlaps the editor corner by 12px)
        grip_x = browser.x + browser.width - 8
        grip_y = browser.y + browser.height - 8
        self.assertIs(self.world.morph_at(grip_x, grip_y), browser)

        self.world.handle_mouse_down(grip_x, grip_y, 0)
        self.assertIs(self.world.hand.drag_target, browser)
        self.assertEqual(self.world.hand.drag_mode, "resize")
        self.world.handle_mouse_move(browser.x + 880, browser.y + 620)
        self.world.handle_mouse_up(browser.x + 880, browser.y + 620, 0)

        self.assertEqual(browser.width, 880.0)
        self.assertEqual(browser.height, 620.0)

        # Verify clicking and scrolling in the newly enlarged bottom-right area of the editor
        enlarged_x = browser.x + 760
        enlarged_y = browser.y + 540
        self.assertIs(self.world.morph_at(enlarged_x, enlarged_y), browser.editor)

        browser.editor.cursor_idx = 0
        self.world.handle_mouse_down(enlarged_x, enlarged_y, 0)
        self.world.handle_mouse_up(enlarged_x, enlarged_y, 0)
        self.assertGreater(browser.editor.cursor_idx, 0)

        browser.editor.scroll_line = 0
        self.world.handle_mouse_wheel(enlarged_x, enlarged_y, 10)
        self.assertGreater(browser.editor.scroll_line, 0)

        # 2. Hot-update Morph & SystemBrowserWindow and verify submorphs are never duplicated
        morph_src = self.smalltalk.get_class_definition_source("Morph")
        self.smalltalk.define_class("Morphic-Core", morph_src)
        self.assertEqual(len(browser.submorphs), 9)
        self.assertIs(self.world.morph_at(enlarged_x, enlarged_y), browser.editor)

        # 3. Alt+Click inside a background window and resize via Halo 'resize' handle
        ws = self.world.submorphs[0]  # WorkspaceWindow is now behind browser
        self.world.handle_mouse_down(ws.x + 400, ws.y + 120, 0, alt_key=True)
        self.assertIsNotNone(self.world.active_halo)
        self.assertIs(self.world.active_halo.target, ws.editor)
        self.assertIs(self.world.submorphs[-1], ws)

        rx, ry = 0.0, 0.0
        for hid, _label, hx, hy, _col in self.world.active_halo._handles():
            if hid == "resize":
                rx, ry = hx, hy
        self.world.handle_mouse_down(rx, ry, 0)
        self.world.handle_mouse_move(ws.x + 700, ws.y + 520)
        self.world.handle_mouse_up(ws.x + 700, ws.y + 520, 0)
        self.assertEqual(ws.width, 700.0)
        self.assertEqual(ws.height, 520.0)
        self.assertIs(self.world.morph_at(ws.x + 620, ws.y + 460), ws.editor)


class TestObjectPondServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        from server import ObjectPondHandler

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ObjectPondHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        from server import BASE_DIR

        cls.server.shutdown()
        cls.server.server_close()
        img_file = BASE_DIR / "objectpond.image"
        if img_file.exists():
            img_file.unlink()

    def test_source_bundle_endpoint(self):
        import json
        import urllib.request

        url = f"http://127.0.0.1:{self.port}/api/source-bundle"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get_content_type(), "application/json")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("objectpond/__init__.py", data)
            self.assertIn("objectpond/kernel/image.py", data)
            self.assertIn("objectpond/morphic/world.py", data)
            self.assertIn("objectpond/tools/browser.py", data)

    def test_image_default_and_save_endpoint(self):
        import json
        import urllib.request

        # GET /api/image/default
        url_get = f"http://127.0.0.1:{self.port}/api/image/default"
        with urllib.request.urlopen(url_get) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get_content_type(), "application/octet-stream")
            raw_bytes = resp.read()
            self.assertGreater(len(raw_bytes), 100)

        # POST /api/image/save
        url_save = f"http://127.0.0.1:{self.port}/api/image/save"
        req = urllib.request.Request(
            url_save,
            data=raw_bytes,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body.get("status"), "ok")
            self.assertEqual(body.get("bytes_saved"), len(raw_bytes))

    def test_changes_and_static_html(self):
        import urllib.request

        url_changes = f"http://127.0.0.1:{self.port}/api/changes"
        with urllib.request.urlopen(url_changes) as resp:
            self.assertEqual(resp.status, 200)

        from objectpond import __version__

        url_html = f"http://127.0.0.1:{self.port}/index.html"
        with urllib.request.urlopen(url_html) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("world-canvas", content)
            self.assertIn("vm.js", content)
            self.assertIn(f"ObjectPond {__version__}", content)
            self.assertNotIn("ObjectPond 1.0", content)



if __name__ == "__main__":
    unittest.main()
