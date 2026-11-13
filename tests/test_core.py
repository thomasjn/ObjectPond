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

        # Redefine Greeter class with new method; existing instance g should migrate __class__
        src_v2 = (
            "class Greeter(Morph):\n"
            "    def __init__(self, x=10, y=10, w=80, h=30):\n"
            "        super().__init__(x, y, w, h)\n"
            "        self.greeting = 'Kia ora'\n"
            "    def speak(self):\n"
            "        return f'[{self.greeting}]'\n"
        )
        cls_v2 = self.smalltalk.define_class("User-Objects", src_v2)
        self.assertIs(g.__class__, cls_v2)
        self.assertEqual(g.speak(), "[Kia ora]")


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
        self.assertEqual(vis, 6)
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


if __name__ == "__main__":
    unittest.main()
