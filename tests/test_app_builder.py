import unittest
from objectpond.boot import create_default_environment
from objectpond.morphic import DisplayCanvas, RecordingBackend
from objectpond.tools.app_builder import AppBuilderWindow, BIND_TARGETS


class TestAppBuilder(unittest.TestCase):
    def setUp(self):
        self.smalltalk, self.world = create_default_environment(1280, 800)
        self.canvas = DisplayCanvas(RecordingBackend(1280, 800))

    def test_palette_drop_grid_snap_smart_guides_and_resize(self):
        builder = self.world.open_app_builder()
        self.assertIsInstance(builder, AppBuilderWindow)

        # 1. Click palette item -> adds snapped widget
        item1 = builder.add_widget_from_palette("TextInputMorph", rel_x=23.0, rel_y=34.0)
        self.assertEqual(item1["x"], 20.0)
        self.assertEqual(item1["y"], 30.0)

        # 2. Drag-and-drop from palette onto design canvas
        pal = builder.palette
        pal.on_mouse_down(pal.x + 20, pal.y + 32, 0)  # LabelMorph
        drop_x = builder.canvas_area.x + 124.0
        drop_y = builder.canvas_area.y + 92.0
        pal.on_mouse_move(drop_x, drop_y, 100, 60)
        self.assertIsNotNone(builder._palette_drag_kind)
        pal.on_mouse_up(drop_x, drop_y, 0)
        self.assertIsNone(builder._palette_drag_kind)
        self.assertEqual(len(builder.canvas_area.items), 2)

        # 3. Drag second widget near x=20 to trigger smart-guide snap to item1's left edge
        ca = builder.canvas_area
        item2 = ca.items[1]
        ca.selected_index = 1
        ca.on_mouse_down(ca.x + item2["x"] + 10, ca.y + item2["y"] + 10, 0)
        target_px = ca.x + 23.0 + 10.0  # within SNAP_TOL=6 of x=20
        ca.on_mouse_move(target_px, ca.y + 100.0, -80, 10)
        self.assertEqual(item2["x"], 20.0)
        self.assertIn(20.0, ca.active_vguides)
        ca.on_mouse_up(target_px, ca.y + 100.0, 0)

        # 4. Resize via bottom-right ('se') handle with 10px grid snap
        hx, hy, hw, hh = ca._handle_rects(item2)["se"]
        ca.on_mouse_down(hx + hw / 2, hy + hh / 2, 0)
        ca.on_mouse_move(hx + 33.0, hy + 14.0, 33.0, 14.0)
        ca.on_mouse_up(hx + 33.0, hy + 14.0, 0)
        self.assertEqual(item2["width"] % 10.0, 0.0)
        self.assertGreater(item2["width"], 140.0)

        builder.full_draw_on(self.canvas)

    def test_bindings_code_generation_and_live_spawn(self):
        builder = self.world.open_app_builder()
        builder.class_name_input.set_text("DemoBoundApp")

        # Add TextInput bound to Instance (self.greeting)
        w_inp = builder.add_widget_from_palette("TextInputMorph", 20, 20)
        builder.outlet_input.set_text("greeting_input", notify=True)
        builder.label_input.set_text("Kia ora", notify=True)
        builder.bind_target_dd.select_index(0, notify=True)  # Instance (self.attr)
        builder.bind_var_input.set_text("greeting", notify=True)

        # Add Slider bound to Class (cls.speed)
        builder.add_widget_from_palette("SliderMorph", 20, 70)
        builder.outlet_input.set_text("speed_slider", notify=True)
        builder.bind_target_dd.select_index(1, notify=True)  # Class (cls.attr)
        builder.bind_var_input.set_text("speed", notify=True)

        # Add Button with action method
        builder.add_widget_from_palette("ButtonMorph", 20, 120)
        builder.outlet_input.set_text("apply_btn", notify=True)
        builder.label_input.set_text("Apply", notify=True)
        builder.action_input.set_text("on_apply", notify=True)

        src = builder.generate_class_source()
        self.assertIn("class DemoBoundApp(SystemWindowMorph):", src)
        self.assertIn("speed = 50.0", src)
        self.assertIn("self.greeting = 'Kia ora'", src)
        self.assertIn("def on_apply(self):", src)

        app = builder.spawn_live_app()
        self.assertIsNotNone(app)
        self.assertIn("DemoBoundApp", self.smalltalk.classes)
        self.assertEqual(app.greeting, "Kia ora")
        self.assertEqual(type(app).speed, 50.0)

        # Two-way binding: UI -> variable
        app.greeting_input.insert_text("!")
        self.assertEqual(app.greeting, "Kia ora!")
        app.speed_slider.set_value(85.0, notify=True)
        self.assertEqual(type(app).speed, 85.0)

        # Two-way binding: variable -> UI on step()
        app.greeting = "Updated"
        type(app).speed = 25.0
        app.step()
        self.assertEqual(app.greeting_input.text, "Updated")
        self.assertEqual(app.speed_slider.value, 25.0)

        self.world.full_draw_on(self.canvas)


if __name__ == "__main__":
    unittest.main()
