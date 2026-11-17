import unittest
from objectpond.kernel.object_memory import SystemDictionary, ChangesLog
from objectpond.kernel.image import ImageSerializer
from objectpond.morphic.canvas import Form, DisplayCanvas, RecordingBackend
from objectpond.morphic.morph import Morph
from objectpond.morphic.world import WorldMorph, HaloMorph
from objectpond.morphic.widgets import (
    SystemWindowMorph,
    ButtonMorph,
    ListMorph,
    CodeEditorMorph,
    MenuMorph,
)


class TestKernelAndObjectMemory(unittest.TestCase):
    def setUp(self):
        self.changes = ChangesLog()
        self.smalltalk = SystemDictionary(changes_log=self.changes)

    def test_register_and_hot_patch_method_on_live_instances(self):
        class CounterMorph(Morph):
            def __init__(self, x=0, y=0, w=50, h=50):
                super().__init__(x, y, w, h)
                self.count = 1

            def compute(self):
                return self.count * 2

        self.smalltalk.register_class("User-Objects", CounterMorph)
        instance = CounterMorph()
        self.assertEqual(instance.compute(), 2)

        # Hot-patch method on live class via SystemDictionary
        new_method_src = (
            "def compute(self):\n"
            "    return self.count * 10 + 5\n"
        )
        self.smalltalk.compile_and_install_method(
            "CounterMorph", "compute", new_method_src, protocol="computing"
        )

        # Existing instance immediately reflects new behavior without recreation
        self.assertEqual(instance.compute(), 15)
        self.assertEqual(
            self.smalltalk.get_method_source("CounterMorph", "compute").strip(),
            new_method_src.strip(),
        )
        self.assertIn("compute", self.smalltalk.get_methods("CounterMorph", protocol="computing"))
        self.assertTrue(len(self.changes.entries) >= 1)

    def test_define_class_and_live_instance_migration(self):
        # Define a new class dynamically from source
        src_v1 = (
            "class Greeter(Morph):\n"
            "    def __init__(self, x=10, y=10, w=80, h=30):\n"
            "        super().__init__(x, y, w, h)\n"
            "        self.greeting = 'Kia ora'\n"
            "    def speak(self):\n"
            "        return self.greeting + '!'\n"
        )
        cls_v1 = self.smalltalk.define_class("User-Objects", src_v1)
        g = cls_v1()
        self.assertEqual(g.speak(), "Kia ora!")
        g.greeting = "Tēnā koe"

        # Redefine Greeter class with new method and new __init__ default;
        # existing instance g migrates __class__ while preserving its live state,
        # while newly created instances use the updated __init__.
        src_v2 = (
            "class Greeter(Morph):\n"
            "    def __init__(self, x=10, y=10, w=80, h=30):\n"
            "        super().__init__(x, y, w, h)\n"
            "        self.greeting = 'Hello'\n"
            "    def speak(self):\n"
            "        return f'[{self.greeting}]'\n"
        )
        cls_v2 = self.smalltalk.define_class("User-Objects", src_v2)
        self.assertIs(g.__class__, cls_v2)
        self.assertEqual(g.speak(), "[Tēnā koe]")
        self.assertEqual(cls_v2().speak(), "[Hello]")


class TestImageSerialization(unittest.TestCase):
    def setUp(self):
        self.changes = ChangesLog()
        self.smalltalk = SystemDictionary(changes_log=self.changes)

    def test_cyclic_world_and_custom_class_snapshot_roundtrip(self):
        world = WorldMorph(800, 600, smalltalk=self.smalltalk)

        # Define a custom Morph subclass in SystemDictionary
        custom_cls_src = (
            "class StarMorph(Morph):\n"
            "    def __init__(self, x=20, y=30, w=40, h=40):\n"
            "        super().__init__(x, y, w, h)\n"
            "        self.energy = 42\n"
            "    def boost(self):\n"
            "        self.energy += 8\n"
            "        return self.energy\n"
        )
        StarMorph = self.smalltalk.define_class("User-Objects", custom_cls_src)
        star = StarMorph(55, 65, 70, 70)
        star.energy = 99
        world.add_morph(star)

        # Add a window with a ButtonMorph whose callback is a bound method on star
        win = SystemWindowMorph("Test Window", 100, 120, 300, 200)
        btn = ButtonMorph("Boost", 110, 160, 80, 28, on_click=star.boost)
        win.add_morph(btn)
        world.add_morph(win)

        # Also add a Form bitmap to star
        star.bitmap = Form(4, 4)
        star.bitmap.put_pixel(1, 2, 0xFF112233)

        # Add workspace globals with shared reference to star
        world.workspace_globals["my_star"] = star
        world.workspace_globals["shared_list"] = [1, 2, star]

        # Serialize to compressed .image bytes
        serializer = ImageSerializer(self.smalltalk)
        raw_bytes = serializer.save_image_bytes(world)
        self.assertIsInstance(raw_bytes, bytes)
        self.assertGreater(len(raw_bytes), 50)

        # Deserialize into a brand-new SystemDictionary and WorldMorph
        new_changes = ChangesLog()
        new_smalltalk = SystemDictionary(changes_log=new_changes)
        restorer = ImageSerializer(new_smalltalk)
        restored_world = restorer.load_image_bytes(raw_bytes)

        self.assertEqual(restored_world.width, 800)
        self.assertEqual(restored_world.height, 600)
        restored_star = restored_world.workspace_globals["my_star"]
        self.assertEqual(restored_star.energy, 99)
        self.assertIs(restored_world.workspace_globals["shared_list"][2], restored_star)
        self.assertIs(restored_star.owner, restored_world)
        self.assertEqual(restored_star.bitmap.pixel_at(1, 2), 0xFF112233)

        # Bound method callback on restored button should invoke restored_star.boost()
        restored_win = [m for m in restored_world.submorphs if isinstance(m, SystemWindowMorph)][0]
        restored_btn = [m for m in restored_win.submorphs if isinstance(m, ButtonMorph)][0]
        restored_btn.trigger()
        self.assertEqual(restored_star.energy, 107)


class TestMorphicAndWidgets(unittest.TestCase):
    def setUp(self):
        self.changes = ChangesLog()
        self.smalltalk = SystemDictionary(changes_log=self.changes)
        self.world = WorldMorph(800, 600, smalltalk=self.smalltalk)
        self.backend = RecordingBackend(800, 600)
        self.canvas = DisplayCanvas(self.backend)

    def test_form_bitblt_operations(self):
        src = Form(10, 10)
        src.fill_rect(0, 0, 10, 10, 0xFFAA0000)
        src.put_pixel(2, 2, 0xFF00FF00)

        dst = Form(20, 20)
        dst.fill_rect(0, 0, 20, 20, 0xFF000000)
        dst.copy_bits(src, 0, 0, 10, 10, 5, 5)

        self.assertEqual(dst.pixel_at(5, 5), 0xFFAA0000)
        self.assertEqual(dst.pixel_at(7, 7), 0xFF00FF00)
        self.assertEqual(dst.pixel_at(0, 0), 0xFF000000)

    def test_morph_hierarchy_hit_testing_and_halos(self):
        win = SystemWindowMorph("Browser", 50, 50, 300, 200)
        btn = ButtonMorph("Click Me", 70, 90, 80, 25)
        clicked = []
        btn.on_click = lambda: clicked.append(True)
        win.add_morph(btn)
        self.world.add_morph(win)

        # Hit test finds deepest visible morph
        hit = self.world.morph_at(80, 100)
        self.assertIs(hit, btn)

        # Dispatch mouse click to button
        self.world.handle_mouse_down(80, 100, button=0, alt_key=False)
        self.world.handle_mouse_up(80, 100, button=0)
        self.assertEqual(clicked, [True])

        # Alt-click spawns a HaloMorph around the target morph
        self.world.handle_mouse_down(80, 100, button=0, alt_key=True)
        self.assertIsNotNone(self.world.active_halo)
        self.assertIsInstance(self.world.active_halo, HaloMorph)
        self.assertIs(self.world.active_halo.target, btn)

        # Hovering over a Halo handle sets hovered_handle and draws tooltip
        inspect_hx, inspect_hy = 0.0, 0.0
        for hid, _label, hx, hy, _col in self.world.active_halo._handles():
            if hid == "inspect":
                inspect_hx, inspect_hy = hx, hy
        self.world.handle_mouse_move(inspect_hx, inspect_hy)
        self.assertEqual(self.world.active_halo.hovered_handle, "inspect")
        self.assertIn("Inspect:", self.world.status_message)

        # Drawing full world executes cleanly on canvas and renders tooltip text
        self.world.full_draw_on(self.canvas)
        self.assertGreater(len(self.backend.commands), 5)
        drawn_texts = [cmd[1] for cmd in self.backend.commands if cmd[0] == "draw_text"]
        self.assertTrue(any("Inspect:" in t for t in drawn_texts))

    def test_code_editor_do_it_print_it_inspect_it(self):
        inspected = []
        editor = CodeEditorMorph(
            10, 10, 400, 200,
            text="a = 6 * 7\na + 8",
            context=self.world.workspace_globals,
            on_inspect=lambda obj: inspected.append(obj),
        )
        # Select all text and Print It
        editor.select_all()
        result_str = editor.print_it()
        self.assertEqual(result_str, "50")
        self.assertEqual(self.world.workspace_globals["a"], 42)
        self.assertIn("50", editor.text)

        # Inspect It on an expression
        editor.set_text("[10, 20, 30]")
        editor.select_all()
        val = editor.inspect_it()
        self.assertEqual(val, [10, 20, 30])
        self.assertEqual(inspected, [[10, 20, 30]])

    def test_code_editor_scrolling_scrollbar_and_auto_scroll(self):
        lines = [f"line_{i:02d} = {'x' * 80}" for i in range(40)]
        editor = CodeEditorMorph(20, 20, 300, 120, text="\n".join(lines))
        self.world.add_morph(editor)

        vis = editor._visible_lines()
        self.assertEqual(vis, 5)
        self.assertEqual(editor.scroll_line, 0)

        # 1. ArrowDown past visible lines auto-scrolls scroll_line
        editor.cursor_idx = 0
        for _ in range(10):
            editor.on_key_down("ArrowDown")
        self.assertGreater(editor.scroll_line, 0)
        row, _col = editor._index_to_row_col(editor.cursor_idx)
        self.assertEqual(row, 10)
        self.assertTrue(editor.scroll_line <= row < editor.scroll_line + vis)

        # 2. PageDown and PageUp scroll by visible lines
        prev_scroll = editor.scroll_line
        editor.on_key_down("PageDown")
        self.assertEqual(editor.scroll_line, prev_scroll + vis)
        editor.on_key_down("PageUp")
        self.assertEqual(editor.scroll_line, prev_scroll)

        # 3. End key on long line auto-scrolls horizontally (scroll_col > 0), Home returns to 0
        editor.on_key_down("End")
        self.assertGreater(editor.scroll_col, 0)
        editor.on_key_down("Home")
        self.assertEqual(editor.scroll_col, 0)

        # 4. Interactive scrollbar thumb drag and track page-click
        sb = editor._scrollbar_geometry()
        self.assertIsNotNone(sb)
        tx, ty, _tw, th, thumb_y, thumb_h = sb
        # Drag thumb to bottom of track
        editor.on_mouse_down(tx + 4, thumb_y + 2, 0)
        editor.on_mouse_move(tx + 4, ty + th, 0, th)
        editor.on_mouse_up(tx + 4, ty + th, 0)
        self.assertEqual(editor.scroll_line, editor._max_scroll_line())

        # Click scrollbar track above thumb to page up
        sb2 = editor._scrollbar_geometry()
        editor.on_mouse_down(tx + 4, ty + 2, 0)
        editor.on_mouse_up(tx + 4, ty + 2, 0)
        self.assertEqual(editor.scroll_line, editor._max_scroll_line() - vis)

        # 5. Resizing editor tall enough to show all lines clamps scroll_line back to 0
        editor.set_extent(300, 900)
        self.assertEqual(editor.scroll_line, 0)

    def test_code_editor_horizontal_scrollbar_only_when_needed(self):
        # Short lines: horizontal scrollbar must NOT appear
        editor = CodeEditorMorph(20, 20, 300, 120, text="a = 1\nb = 2\n")
        self.world.add_morph(editor)
        self.assertIsNone(editor._hscrollbar_geometry())
        self.assertEqual(editor._visible_lines(), 6)

        # Long line: horizontal scrollbar appears, reserves bottom height, and supports drag/click
        editor.set_text("short\n" + ("x" * 120))
        hsb = editor._hscrollbar_geometry()
        self.assertIsNotNone(hsb)
        self.assertEqual(editor._visible_lines(), 5)

        tx, ty, tw, _th, thumb_x, _thumb_w = hsb
        # Drag thumb to right end of track
        editor.on_mouse_down(thumb_x + 2, ty + 4, 0)
        editor.on_mouse_move(tx + tw, ty + 4, tw, 0)
        editor.on_mouse_up(tx + tw, ty + 4, 0)
        self.assertEqual(editor.scroll_col, editor._max_scroll_col())

        # Click track to the left of thumb to page left
        editor.on_mouse_down(tx + 2, ty + 4, 0)
        editor.on_mouse_up(tx + 2, ty + 4, 0)
        self.assertEqual(
            editor.scroll_col,
            max(0, editor._max_scroll_col() - editor._visible_cols()),
        )

        # Draw on canvas without error and verify horizontal scrollbar is rendered
        self.backend.commands.clear()
        editor.draw_on(self.canvas)
        self.assertTrue(
            any(
                cmd[0] == "fill_rect" and cmd[1] == tx and cmd[2] == ty and cmd[3] == tw
                for cmd in self.backend.commands
            )
        )

        # Replacing with short text hides horizontal scrollbar and clamps scroll_col to 0
        editor.set_text("hello")
        self.assertIsNone(editor._hscrollbar_geometry())
        self.assertEqual(editor.scroll_col, 0)
        self.backend.commands.clear()
        editor.draw_on(self.canvas)
        self.assertFalse(
            any(
                cmd[0] == "fill_rect" and cmd[2] == ty
                for cmd in self.backend.commands
            )
        )

        # Resizing wide enough hides horizontal scrollbar
        editor.set_text("x" * 60)
        self.assertIsNotNone(editor._hscrollbar_geometry())
        editor.scroll_col = 10
        editor.set_extent(800, 120)
        self.assertIsNone(editor._hscrollbar_geometry())
        self.assertEqual(editor.scroll_col, 0)

    def test_code_editor_cut_copy_paste_and_world_clipboard(self):
        ed1 = CodeEditorMorph(10, 10, 260, 120, text="hello world")
        ed2 = CodeEditorMorph(10, 150, 260, 120, text="prefix ")
        self.world.add_morph(ed1)
        self.world.add_morph(ed2)

        # Copy selection from ed1 via Cmd/Ctrl+C
        self.world.hand.keyboard_focus = ed1
        ed1.selection_start = 6
        ed1.selection_end = 11
        ed1.cursor_idx = 11
        self.world.handle_key_down("c", meta_key=True)
        self.assertEqual(self.world.get_clipboard_text(), "world")
        self.assertEqual(ed1.text, "hello world")

        # Empty selection copy/cut should not clobber clipboard
        ed1.selection_start = None
        ed1.selection_end = None
        self.world.handle_key_down("c", ctrl_key=True)
        self.assertEqual(self.world.get_clipboard_text(), "world")

        # Paste into ed2 via Ctrl+V
        self.world.hand.keyboard_focus = ed2
        ed2.cursor_idx = len(ed2.text)
        self.world.handle_key_down("v", ctrl_key=True)
        self.assertEqual(ed2.text, "prefix world")

        # Cut selection from ed2 via Cmd+X and paste back into ed1
        ed2.selection_start = 0
        ed2.selection_end = 7
        self.world.handle_key_down("x", meta_key=True)
        self.assertEqual(ed2.text, "world")
        self.assertEqual(self.world.get_clipboard_text(), "prefix ")

        self.world.hand.keyboard_focus = ed1
        ed1.selection_start = 0
        ed1.selection_end = 0
        ed1.cursor_idx = 0
        self.world.handle_key_down("v", meta_key=True)
        self.assertEqual(ed1.text, "prefix hello world")

        # Browser-style handle_paste normalizes CRLF and updates clipboard
        self.world.handle_paste("line1\r\nline2")
        self.assertEqual(self.world.get_clipboard_text(), "line1\r\nline2")
        self.assertIn("line1\nline2", ed1.text)

    def test_code_editor_autocomplete(self):
        ed = CodeEditorMorph(10, 40, 360, 200, text="", context={"my_custom_var": 42})
        self.world.add_morph(ed)
        self.world.hand.keyboard_focus = ed

        # 1. Identifier prefix completion (2+ chars) and Tab acceptance
        for ch in "my_cu":
            ed.on_key_down(ch)
        self.assertIn("my_custom_var", ed._ac_items)
        ed.on_key_down("Tab")
        self.assertEqual(ed.text, "my_custom_var")
        self.assertEqual(ed._ac_items, [])

        # 2. Dotted attribute completion on live World object
        ed.set_text("")
        for ch in "World.open_w":
            ed.on_key_down(ch)
        self.assertIn("open_workspace", ed._ac_items)
        ed.draw_on(self.canvas)
        ed.on_key_down("Enter")
        self.assertEqual(ed.text, "World.open_workspace")

        # 3. Ctrl+Space manual trigger & Escape dismissal
        ed.set_text("")
        ed.on_key_down(" ", ctrl_key=True)
        self.assertTrue(len(ed._ac_items) > 0)
        ed.on_key_down("Escape")
        self.assertEqual(ed._ac_items, [])

    def test_code_editor_double_click_word_selection(self):
        ed = CodeEditorMorph(x=0, y=0, width=400, height=160, text="alpha_one = beta_two + 42")
        self.world.add_morph(ed)
        # Click inside 'beta_two' (starts at index 12)
        cx = ed.x + ed.GUTTER_WIDTH + 6.0 + 14 * ed.CHAR_WIDTH
        cy = ed.y + 10.0
        ed.on_mouse_down(cx, cy, 0)
        ed.on_mouse_up(cx, cy, 0)
        self.assertFalse(ed.has_selection())
        ed.on_mouse_down(cx, cy, 0)
        ed.on_mouse_move(cx + 1.0, cy, 1.0, 0.0)
        ed.on_mouse_up(cx + 1.0, cy, 0)
        lo, hi = ed.get_selection_range()
        self.assertEqual(ed.text[lo:hi], "beta_two")

    def test_transient_attrs_and_changes_compact(self):
        class BaseCachedMorph(Morph):
            _transient_attrs = ("_base_cache",)

            def __init__(self):
                super().__init__(0, 0, 50, 50)
                self._base_cache = "big_base_data"
                self.label = "keep_me"

        class ChildCachedMorph(BaseCachedMorph):
            _transient_attrs = ("_child_cache",)

            def __init__(self):
                super().__init__()
                self._child_cache = [1, 2, 3]
                self._inst_cache = "also_transient"
                self._transient_attrs = ("_inst_cache",)

        from objectpond.kernel.image import ImageSerializer

        self.smalltalk.register_class("User-Objects", BaseCachedMorph)
        self.smalltalk.register_class("User-Objects", ChildCachedMorph)
        m = ChildCachedMorph()
        self.world.add_morph(m)
        serializer = ImageSerializer(self.smalltalk)
        raw = serializer.save_image_bytes(self.world)
        restored_world = serializer.load_image_bytes(raw)
        restored_m = [x for x in restored_world.submorphs if isinstance(x, ChildCachedMorph)][0]
        self.assertEqual(restored_m.label, "keep_me")
        self.assertFalse(hasattr(restored_m, "_base_cache"))
        self.assertFalse(hasattr(restored_m, "_child_cache"))
        self.assertFalse(hasattr(restored_m, "_inst_cache"))

        # ChangesLog.compact keeps only latest class/method per target and preserves doit
        self.smalltalk.changes_log.record("method", "Foo>>bar", "def bar(self): return 1")
        self.smalltalk.changes_log.record("doit", "Workspace", "1 + 1")
        self.smalltalk.changes_log.record("method", "Foo>>bar", "def bar(self): return 2")
        removed = self.smalltalk.changes_log.compact()
        self.assertGreaterEqual(removed, 1)
        foo_entries = [e for e in self.smalltalk.changes_log.entries if e.get("target") == "Foo>>bar"]
        self.assertEqual(len(foo_entries), 1)
        self.assertIn("return 2", foo_entries[0]["source"])
        self.assertTrue(any(e.get("kind") == "doit" and e.get("source") == "1 + 1" for e in self.smalltalk.changes_log.entries))


if __name__ == "__main__":
    unittest.main()
