import unittest
from objectpond.boot import create_default_environment
from objectpond.morphic import (
    ButtonMorph,
    CheckboxMorph,
    ColumnMorph,
    DialogMorph,
    DisplayCanvas,
    DropdownMorph,
    Form,
    ImageMorph,
    LabelMorph,
    ProgressBarMorph,
    RecordingBackend,
    RowMorph,
    ScrollPaneMorph,
    SliderMorph,
    SplitPaneMorph,
    TabViewMorph,
    TableMorph,
    TextInputMorph,
    ToggleSwitchMorph,
    TreeMorph,
    WorldMorph,
)
from objectpond.tools.demos import WidgetShowcaseWindow


class TestAppWidgetsAndContainers(unittest.TestCase):
    def setUp(self):
        self.world = WorldMorph(width=900, height=650)
        self.canvas = DisplayCanvas(RecordingBackend(900, 650))

    def test_text_input_editing_submit_and_clipboard(self):
        submitted = []
        changed = []
        inp = TextInputMorph(
            10, 40, 180, 28,
            text="abc",
            placeholder="enter",
            on_change=changed.append,
            on_submit=submitted.append,
        )
        self.world.add_morph(inp)
        self.world.hand.keyboard_focus = inp

        inp.on_key_down("d")
        self.assertEqual(inp.text, "abcd")
        self.assertEqual(changed[-1], "abcd")

        inp.on_key_down("a", ctrl_key=True)
        inp.on_key_down("c", meta_key=True)
        self.assertEqual(self.world.get_clipboard_text(), "abcd")

        inp.on_key_down("x", ctrl_key=True)
        self.assertEqual(inp.text, "")
        self.world.handle_paste("hi\nthere")
        self.assertEqual(inp.text, "hi there")

        inp.on_key_down("Enter")
        self.assertEqual(submitted, ["hi there"])
        inp.draw_on(self.canvas)

    def test_checkbox_toggle_slider_dropdown_progress_image(self):
        cb_vals = []
        cb = CheckboxMorph(10, 40, 150, 24, label="Flag", checked=False, on_change=cb_vals.append)
        cb.on_mouse_down(15, 50, 0)
        self.assertTrue(cb.checked)
        self.assertEqual(cb_vals, [True])

        tg_vals = []
        tg = ToggleSwitchMorph(10, 70, 150, 24, label="Mode", checked=True, on_change=tg_vals.append)
        tg.on_mouse_down(15, 80, 0)
        self.assertFalse(tg.checked)
        self.assertEqual(tg_vals, [False])

        sl_vals = []
        sl = SliderMorph(10, 100, 180, 26, min_val=0, max_val=100, value=20, step=5, on_change=sl_vals.append)
        sl.on_mouse_down(150, 113, 0)
        sl.on_mouse_up(150, 113, 0)
        self.assertGreater(sl.value, 50)
        self.assertTrue(sl_vals)

        dd_vals = []
        dd = DropdownMorph(10, 140, 160, 28, options=["One", "Two", "Three"], on_change=lambda i, v: dd_vals.append((i, v)))
        self.world.add_morph(dd)
        dd.on_mouse_down(20, 150, 0)
        self.assertIsNotNone(self.world.active_menu)
        self.world.handle_mouse_down(25, 198, 0)  # clicks "Two"
        self.assertEqual(dd.selected_index, 1)
        self.assertEqual(dd_vals[-1], (1, "Two"))

        pb = ProgressBarMorph(10, 180, 180, 20, value=0.5, indeterminate=True)
        pb.step()
        self.assertGreater(pb._phase, 0.0)

        img = ImageMorph(10, 210, 48, 48, form=Form(20, 20, 0xFF88C0D0))
        for m in (cb, tg, sl, dd, pb, img):
            m.draw_on(self.canvas)

    def test_layout_scroll_tabs_split_table_tree_dialog(self):
        row = RowMorph(0, 0, 300, 40, padding=4, spacing=8)
        b1 = ButtonMorph("A", 0, 0, 80, 28)
        b2 = ButtonMorph("B", 0, 0, 80, 28)
        row.add_child(b1)
        row.add_child(b2, flex=1)
        self.assertAlmostEqual(b1.width, 80.0)
        self.assertGreater(b2.width, 180.0)

        col = ColumnMorph(0, 0, 180, 400, padding=8, spacing=8)
        col.add_child(LabelMorph("Top", 0, 0))
        scroll = ScrollPaneMorph(10, 40, 220, 150, content=col)
        self.assertIsNone(scroll._hsb_geometry())
        self.assertIsNotNone(scroll._vsb_geometry())
        col.set_extent(260, 400)
        self.assertIsNotNone(scroll._hsb_geometry())
        scroll.on_mouse_wheel(30, 80, 40.0)
        self.assertGreater(scroll.scroll_y, 0.0)
        scroll.full_draw_on(self.canvas)

        pane1 = LabelMorph("P1", 0, 0)
        pane2 = LabelMorph("P2", 0, 0)
        tabs = TabViewMorph(10, 40, 300, 200, tabs=[("One", pane1), ("Two", pane2)])
        self.assertTrue(pane1.visible)
        self.assertFalse(pane2.visible)
        tabs.on_mouse_down(160, 50, 0)
        self.assertEqual(tabs.active_index, 1)
        self.assertTrue(pane2.visible)
        tabs.full_draw_on(self.canvas)

        left = LabelMorph("L", 0, 0)
        right = LabelMorph("R", 0, 0)
        split = SplitPaneMorph(10, 40, 300, 180, first=left, second=right, ratio=0.3)
        sx, sy, _sw, _sh = split._splitter_rect()
        split.on_mouse_down(sx + 2, sy + 10, 0)
        split.on_mouse_move(200, sy + 10, 50, 0)
        split.on_mouse_up(200, sy + 10, 0)
        self.assertGreater(split.ratio, 0.5)
        split.full_draw_on(self.canvas)

        table = TableMorph(10, 40, 260, 140, columns=["Name", "Score"], rows=[["Zed", 2], ["Ada", 9]])
        table.on_mouse_down(20, 50, 0)  # sort by Name
        self.assertEqual(table.rows[0][0], "Ada")
        table.on_mouse_down(20, 70, 0)  # select row 0
        self.assertEqual(table.selected_row, 0)
        table.draw_on(self.canvas)

        tree = TreeMorph(
            10, 40, 200, 140,
            nodes=[{"label": "Root", "expanded": False, "children": [{"label": "Child", "children": []}]}],
        )
        self.assertEqual(len(tree._flat_visible()), 1)
        tree.on_mouse_down(15, 50, 0)  # expand Root
        self.assertEqual(len(tree._flat_visible()), 2)
        tree.draw_on(self.canvas)

        applied = []
        dlg = DialogMorph(
            title="Prompt",
            message="Name?",
            input_default="World",
            buttons=[("OK", applied.append), ("Cancel", None)],
        )
        self.world.open_modal(dlg)
        self.assertIs(self.world.active_modal, dlg)
        self.world.full_draw_on(self.canvas)
        ok_btn = [m for m in dlg.submorphs if isinstance(m, ButtonMorph) and m.label == "OK"][0]
        self.world.handle_mouse_down(ok_btn.x + 5, ok_btn.y + 5, 0)
        self.world.handle_mouse_up(ok_btn.x + 5, ok_btn.y + 5, 0)
        self.assertIsNone(self.world.active_modal)
        self.assertEqual(applied, ["World"])

    def test_widget_showcase_window_boot_and_interaction(self):
        smalltalk, world = create_default_environment(1280, 800)
        self.assertIn("TextInputMorph", smalltalk.classes)
        self.assertIn("WidgetShowcaseWindow", smalltalk.classes)

        win = world.spawn_widget_showcase()
        self.assertIsInstance(win, WidgetShowcaseWindow)
        win.slider.set_value(80)
        self.assertAlmostEqual(win.progress.value, 0.8)
        win.tabs.select_tab(1)
        self.assertEqual(win.tabs.active_index, 1)
        win.set_extent(680, 480)
        world.full_draw_on(self.canvas)


if __name__ == "__main__":
    unittest.main()
