from typing import Any, Callable, Dict, List, Optional, Tuple
from .canvas import DisplayCanvas, Form
from .morph import Morph


class HandMorph(Morph):
    """Represents the user's cursor, active drag target, and keyboard focus."""

    def __init__(self):
        super().__init__(0, 0, 12, 18, color="#ffffff", border_width=0)
        self.drag_target: Optional[Morph] = None
        self.drag_mode: str = "move"  # "move", "resize", or "custom"
        self.pressed_morph: Optional[Morph] = None
        self.keyboard_focus: Optional[Morph] = None
        self.last_x: float = 0.0
        self.last_y: float = 0.0


class HaloMorph(Morph):
    """
    Classic Morphic Halo displayed around any Morph when Alt-clicked (or Middle-clicked).
    Provides circular colored handles for Inspect, Browse, Move, Duplicate, Color, Resize, and Delete.
    """

    HANDLE_RADIUS = 11.0
    HANDLE_TOOLTIPS: Dict[str, str] = {
        "delete": "Delete: Remove Morph from World",
        "inspect": "Inspect: Open Object Inspector on Morph",
        "browse": "Browse: Open Class in System Browser",
        "move": "Move: Drag to reposition Morph",
        "duplicate": "Duplicate: Clone this Morph",
        "color": "Color: Cycle Morph fill color",
        "resize": "Resize: Drag to resize Morph",
    }

    def __init__(self, target: Morph):
        super().__init__(
            target.x - 16,
            target.y - 28,
            target.width + 32,
            target.height + 48,
            color="",
            border_color="#88c0d0",
            border_width=1.5,
        )
        self.target = target
        self.active_handle: Optional[str] = None
        self.hovered_handle: Optional[str] = None
        self.hover_x: float = 0.0
        self.hover_y: float = 0.0

    def tooltip_for(self, handle_id: Optional[str]) -> Optional[str]:
        if handle_id is None:
            return None
        return self.HANDLE_TOOLTIPS.get(handle_id, handle_id.capitalize())

    def update_hover(self, px: float, py: float) -> bool:
        prev = getattr(self, "hovered_handle", None)
        cur = self.handle_at(px, py)
        self.hovered_handle = cur
        self.hover_x = px
        self.hover_y = py
        return prev != cur or cur is not None

    def sync_to_target(self) -> None:
        self.x = self.target.x - 16
        self.y = self.target.y - 28
        self.width = self.target.width + 32
        self.height = self.target.height + 48

    def _handles(self) -> List[Tuple[str, str, float, float, str]]:
        """Returns (id, label, cx, cy, fill_color) for each circular halo handle."""
        self.sync_to_target()
        tx, ty, tw, th = self.target.x, self.target.y, self.target.width, self.target.height
        return [
            ("delete", "X", tx - 8, ty - 8, "#ff5c8a"),
            ("inspect", "I", tx - 8, ty + th / 2, "#38b6ff"),
            ("browse", "B", tx + tw / 3, ty - 12, "#9b5de5"),
            ("move", "M", tx + tw * 2 / 3, ty - 12, "#d4a373"),
            ("duplicate", "D", tx + tw + 8, ty - 8, "#2ec4b6"),
            ("color", "C", tx + tw + 8, ty + th / 2, "#ff9f1c"),
            ("resize", "R", tx + tw + 8, ty + th + 8, "#ffd166"),
        ]

    def handle_at(self, px: float, py: float) -> Optional[str]:
        r2 = (self.HANDLE_RADIUS + 3) ** 2
        for hid, _label, cx, cy, _col in self._handles():
            if (px - cx) ** 2 + (py - cy) ** 2 <= r2:
                return hid
        return None

    def contains_point(self, px: float, py: float) -> bool:
        return self.handle_at(px, py) is not None

    def draw_on(self, canvas: DisplayCanvas) -> None:
        self.sync_to_target()
        tx, ty, tw, th = self.target.x, self.target.y, self.target.width, self.target.height
        canvas.stroke_rect(tx - 3, ty - 3, tw + 6, th + 6, "#88c0d0", 1.5)

        hovered_id = getattr(self, "hovered_handle", None)
        hovered_info: Optional[Tuple[str, float, float, str]] = None

        for hid, label, cx, cy, fill_color in self._handles():
            is_hovered = hid == hovered_id
            radius = self.HANDLE_RADIUS + 2.0 if is_hovered else self.HANDLE_RADIUS
            stroke_col = "#ffffff" if is_hovered else "#1d2021"
            stroke_w = 2.0 if is_hovered else 1.5
            canvas.fill_circle(cx, cy, radius, fill_color, stroke_col, stroke_w)
            canvas.draw_text(
                label,
                cx - 4,
                cy + 4,
                color="#111111",
                font="bold 11px monospace",
            )
            if is_hovered:
                hovered_info = (hid, cx, cy, fill_color)

        # Draw target class & identity badge at bottom of Halo
        caption = f"{self.target.__class__.__name__} ({int(tw)}x{int(th)})"
        badge_w = len(caption) * 7.5 + 14
        bx = tx + (tw - badge_w) / 2
        by = ty + th + 12
        canvas.fill_round_rect(bx, by, badge_w, 20, 4, "#1e222a", "#88c0d0", 1.0)
        canvas.draw_text(caption, bx + 7, by + 14, color="#eceff4", font="11px monospace")

        # Draw floating tooltip bubble when hovering over a Halo handle
        if hovered_info is not None:
            hid, hcx, hcy, hcol = hovered_info
            tip_text = self.tooltip_for(hid) or hid
            tip_w = len(tip_text) * 7.4 + 16.0
            tip_h = 22.0
            tip_x = max(6.0, hcx - tip_w / 2.0)
            tip_y = hcy - self.HANDLE_RADIUS - tip_h - 6.0
            if tip_y < 32.0:
                tip_y = hcy + self.HANDLE_RADIUS + 8.0
            canvas.fill_round_rect(tip_x, tip_y, tip_w, tip_h, 4.0, "#14171d", hcol, 1.5)
            canvas.draw_text(
                tip_text,
                tip_x + 8.0,
                tip_y + 15.0,
                color="#eceff4",
                font="11px monospace",
            )


class TranscriptProxy:
    """Provides `Transcript.show(...)` and `Transcript.clear()` inside the image."""

    def __init__(self, world: "WorldMorph"):
        self._world = world

    def show(self, *args: Any) -> None:
        msg = " ".join(str(a) for a in args)
        if self._world.smalltalk:
            self._world.smalltalk.log_transcript(msg)
        self._world.changed()

    def cr(self) -> None:
        self.show("")

    def clear(self) -> None:
        if self._world.smalltalk:
            self._world.smalltalk.transcript_history.clear()
        self._world.changed()


class WorldMorph(Morph):
    """
    Root desktop environment Morph in ObjectPond.
    Manages the top docking bar, submorph windows, HandMorph event routing,
    HaloMorph live manipulation, stepping animations, and global Workspace bindings.
    """

    MENUBAR_HEIGHT = 28.0

    def __init__(
        self,
        width: float = 1200,
        height: float = 800,
        smalltalk: Optional[Any] = None,
    ):
        super().__init__(
            0,
            0,
            width,
            height,
            color="#242933",
            border_color="#242933",
            border_width=0,
        )
        self.corner_radius = 0.0
        self.smalltalk = smalltalk
        self.hand = HandMorph()
        self.active_halo: Optional[HaloMorph] = None
        self.active_menu: Optional[Morph] = None
        self.active_modal: Optional[Morph] = None
        self.workspace_globals: Dict[str, Any] = {}
        self.status_message: str = "Ready — Alt+Click any Morph for Morphic Halos"
        self.stepping_paused: bool = False
        self.clipboard_text: str = ""
        self._clipboard_seq: int = 0
        self._host_action_callback: Optional[Callable[[str, Any], None]] = None
        self.bind_smalltalk(smalltalk)

    def bind_smalltalk(self, smalltalk: Optional[Any]) -> None:
        self.smalltalk = smalltalk
        from .sound import SampledSound, SoundSynth, ADSR

        transcript = TranscriptProxy(self)
        self.workspace_globals["World"] = self
        self.workspace_globals["Transcript"] = transcript
        self.workspace_globals["Form"] = Form
        self.workspace_globals["Morph"] = Morph
        self.workspace_globals["SampledSound"] = SampledSound
        self.workspace_globals["SoundSynth"] = SoundSynth
        self.workspace_globals["ADSR"] = ADSR
        if smalltalk is not None:
            self.workspace_globals["Smalltalk"] = smalltalk
            smalltalk.global_namespace["World"] = self
            smalltalk.global_namespace["Transcript"] = transcript
            smalltalk.global_namespace["Form"] = Form
            smalltalk.global_namespace["Morph"] = Morph
            smalltalk.global_namespace["SampledSound"] = SampledSound
            smalltalk.global_namespace["SoundSynth"] = SoundSynth
            smalltalk.global_namespace["ADSR"] = ADSR
            for cls_name, rec in smalltalk.classes.items():
                self.workspace_globals.setdefault(cls_name, rec.cls_obj)

    def set_host_action_callback(self, callback: Callable[[str, Any], None]) -> None:
        self._host_action_callback = callback

    def trigger_host_action(self, action: str, payload: Any = None) -> None:
        if self._host_action_callback is not None:
            self._host_action_callback(action, payload)

    def play_sound(self, sound: Any) -> bool:
        """Plays a SampledSound via the browser Web Audio host bridge (or no-op headless)."""
        if sound is None or not hasattr(sound, "to_pcm_b64"):
            return False
        payload = {
            "pcm_b64": sound.to_pcm_b64(),
            "sample_rate": getattr(sound, "sample_rate", 44100),
            "channels": getattr(sound, "channels", 1),
        }
        self.trigger_host_action("play_sound", payload)
        return True

    def _menubar_items(self) -> List[Tuple[str, str, float, float]]:
        items = [
            ("objectpond", "ObjectPond", 10),
            ("browser", "System Browser", 102),
            ("workspace", "Workspace", 232),
            ("inspector", "Inspector", 326),
            ("transcript", "Transcript", 414),
            ("changes", "Changes", 506),
            ("bouncing", "+ Atoms Morph", 588),
            ("paint", "+ BitBlt Paint", 710),
            ("save_image", "Save Image", 830),
            ("export_image", "Export .image", 930),
            ("load_image", "Load .image", 1054),
            ("import_object", "Import Object", 1166),
        ]
        result = []
        for idx, (action_id, label, x_pos) in enumerate(items):
            next_x = items[idx + 1][2] if idx + 1 < len(items) else x_pos + len(label) * 8 + 20
            result.append((action_id, label, float(x_pos), float(next_x - x_pos - 6)))
        return result

    def draw_on(self, canvas: DisplayCanvas) -> None:
        # 1. Desktop background with subtle dot grid
        canvas.fill_rect(0, 0, self.width, self.height, self.color)
        grid_step = 32
        for gx in range(grid_step, int(self.width), grid_step):
            for gy in range(int(self.MENUBAR_HEIGHT) + grid_step, int(self.height), grid_step):
                canvas.fill_rect(gx, gy, 1.5, 1.5, "#2e3440")

    def full_draw_on(self, canvas: DisplayCanvas) -> None:
        self.draw_on(canvas)
        for sub in self.submorphs:
            if sub.visible:
                sub.full_draw_on(canvas)

        # Draw top menu bar on top of desktop
        self._draw_menubar(canvas)

        # Draw active modal dialog if present
        modal = getattr(self, "active_modal", None)
        if modal is not None and modal.visible:
            canvas.fill_rect(0, 0, self.width, self.height, "rgba(15, 19, 26, 0.55)")
            modal.full_draw_on(canvas)

        # Draw active context menu if present
        if self.active_menu is not None and self.active_menu.visible:
            self.active_menu.full_draw_on(canvas)

        # Draw active Morphic Halo if present
        if self.active_halo is not None:
            if self.active_halo.target.owner is None and self.active_halo.target is not self:
                self.active_halo = None
            else:
                self.active_halo.draw_on(canvas)

        self.is_damaged = False

    def _draw_menubar(self, canvas: DisplayCanvas) -> None:
        canvas.fill_rect(0, 0, self.width, self.MENUBAR_HEIGHT, "#1b1f27")
        canvas.draw_line(0, self.MENUBAR_HEIGHT, self.width, self.MENUBAR_HEIGHT, "#3b4252", 1.0)

        for action_id, label, bx, bw in self._menubar_items():
            is_brand = action_id == "objectpond"
            is_save = action_id in ("save_image", "export_image", "load_image", "import_object")
            bg = "#3b4252" if is_brand else ("#2a4d3e" if is_save else "#252b37")
            fg = "#88c0d0" if is_brand else ("#a3be8c" if is_save else "#e5e9f0")
            canvas.fill_round_rect(bx, 3, bw, 22, 4, bg, "#434c5e", 1.0)
            font = "bold 12px monospace" if is_brand else "12px monospace"
            canvas.draw_text(label, bx + 8, 18, color=fg, font=font)

        # Right-aligned status message
        status_w = len(self.status_message) * 7.2
        if self.width - status_w > 1295:
            canvas.draw_text(
                self.status_message,
                self.width - status_w - 14,
                18,
                color="#81a1c1",
                font="11px monospace",
            )

    def _step_morphs_once(self) -> None:
        for m in self.all_morphs():
            if m.visible and m.wants_steps():
                try:
                    m.step()
                except Exception as exc:
                    if self.smalltalk:
                        self.smalltalk.record_exception(
                            exc,
                            context=f"step:{m.__class__.__name__}",
                            target=m,
                        )
                        self.smalltalk.log_transcript(f"Step error in {m}: {exc}")

    def step_once(self, canvas: Optional[DisplayCanvas] = None) -> bool:
        """Executes a single step pass regardless of stepping_paused and redraws if damaged."""
        self._step_morphs_once()
        if canvas is not None and self.is_damaged:
            self.full_draw_on(canvas)
            return True
        return False

    def step_n(self, count: int = 1, canvas: Optional[DisplayCanvas] = None) -> int:
        """Executes `count` step cycles and returns the number of cycles run."""
        n = max(0, int(count))
        for _ in range(n):
            self._step_morphs_once()
        if canvas is not None and self.is_damaged:
            self.full_draw_on(canvas)
        return n

    def do_one_cycle(self, canvas: Optional[DisplayCanvas] = None) -> bool:
        """Executes one World cycle: steps active morphs (unless paused) and redraws if damaged."""
        if not getattr(self, "stepping_paused", False):
            self._step_morphs_once()

        if canvas is not None and self.is_damaged:
            self.full_draw_on(canvas)
            return True
        return False

    def contains_point(self, px: float, py: float) -> bool:
        return self.visible and px >= 0 and py >= 0

    # --- Event Routing ---
    def handle_mouse_down(
        self,
        px: float,
        py: float,
        button: int = 0,
        alt_key: bool = False,
        shift_key: bool = False,
    ) -> None:
        self.hand.last_x = px
        self.hand.last_y = py

        # 1. Check if clicking inside an active Halo handle
        if self.active_halo is not None:
            hid = self.active_halo.handle_at(px, py)
            if hid is not None:
                win = self._enclosing_window(self.active_halo.target)
                if win is not None:
                    win.bring_to_front()
                self._activate_halo_handle(hid, px, py)
                self.changed()
                return
            self.active_halo = None
            self.changed()

        # 2. Check if clicking inside an active popup menu
        if self.active_menu is not None and self.active_menu.visible:
            if self.active_menu.contains_point(px, py):
                self.active_menu.on_mouse_down(px, py, button)
                self.active_menu = None
                self.changed()
                return
            self.active_menu = None
            self.changed()

        # 2.5. Route clicks exclusively to active modal dialog if open
        modal = getattr(self, "active_modal", None)
        if modal is not None and modal.visible:
            if modal.contains_point(px, py):
                m_target = modal.morph_at(px, py) or modal
                self.hand.keyboard_focus = m_target
                self.hand.pressed_morph = m_target
                m_target.on_mouse_down(px, py, button)
            self.changed()
            return

        # 3. Check top menubar click
        if py <= self.MENUBAR_HEIGHT and not alt_key:
            for action_id, _label, bx, bw in self._menubar_items():
                if bx <= px <= bx + bw:
                    self._execute_menubar_action(action_id)
                    self.changed()
                    return

        # 4. Find deepest visible Morph under cursor
        target = self.morph_at(px, py) or self

        # 5. Alt-Click or Middle-Click (button == 1) spawns Morphic Halo on target!
        if (alt_key or button == 1) and target is not self:
            win = self._enclosing_window(target)
            if win is not None:
                win.bring_to_front()
            self.active_halo = HaloMorph(target)
            self.status_message = f"Halo on {target.__class__.__name__}"
            self.changed()
            return

        # 6. Right-click on desktop opens World Menu
        if button == 2 and target is self:
            self._open_world_menu(px, py)
            self.changed()
            return

        # 7. Promote enclosing window to front
        win = self._enclosing_window(target)
        if win is not None:
            win.bring_to_front()

        # 8. Assign keyboard focus if target accepts text/keys
        self.hand.keyboard_focus = target
        self.hand.pressed_morph = target
        target.on_mouse_down(px, py, button)

        # If target is a plain user Morph directly on the World (not inside a widget
        # and not actively capturing mouse-move events such as painting), allow dragging it
        if (
            self.hand.drag_target is None
            and target is not self
            and target.owner is self
            and target.__class__.__name__ != "SystemWindowMorph"
            and not getattr(target, "is_painting", False)
            and not (hasattr(target, "wants_mouse_drag") and target.wants_mouse_drag(px, py))
        ):
            self.hand.drag_target = target
            self.hand.drag_mode = "move"

        self.changed()

    def handle_mouse_move(self, px: float, py: float) -> None:
        dx = px - self.hand.last_x
        dy = py - self.hand.last_y
        self.hand.last_x = px
        self.hand.last_y = py

        if self.hand.drag_target is not None:
            t = self.hand.drag_target
            if self.hand.drag_mode == "move":
                t.move_by(dx, dy)
            elif self.hand.drag_mode == "resize":
                new_w = max(80.0, px - t.x)
                new_h = max(50.0, py - t.y)
                t.set_extent(new_w, new_h)
            self.changed()
            return

        if self.hand.pressed_morph is not None:
            self.hand.pressed_morph.on_mouse_move(px, py, dx, dy)
            self.changed()
            return

        if self.active_halo is not None:
            if self.active_halo.update_hover(px, py):
                tip = self.active_halo.tooltip_for(self.active_halo.hovered_handle)
                if tip:
                    self.status_message = tip
                else:
                    self.status_message = f"Halo on {self.active_halo.target.__class__.__name__}"
                self.changed()

    def handle_mouse_up(self, px: float, py: float, button: int = 0) -> None:
        self.hand.last_x = px
        self.hand.last_y = py
        self.hand.drag_target = None
        if self.hand.pressed_morph is not None:
            m = self.hand.pressed_morph
            self.hand.pressed_morph = None
            m.on_mouse_up(px, py, button)
            self.changed()

    def handle_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        target = self.morph_at(px, py)
        if target is not None and target is not self:
            target.on_mouse_wheel(px, py, delta_y)
            self.changed()

    def get_clipboard_text(self) -> str:
        return getattr(self, "clipboard_text", "")

    def set_clipboard_text(self, text: str) -> None:
        self.clipboard_text = str(text)
        self._clipboard_seq = getattr(self, "_clipboard_seq", 0) + 1

    def handle_paste(self, text: str) -> None:
        pasted = str(text)
        self.set_clipboard_text(pasted)
        if self.hand.keyboard_focus is not None:
            self.hand.keyboard_focus.on_paste(pasted)
            self.changed()

    def handle_key_down(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> None:
        if self.hand.keyboard_focus is not None:
            self.hand.keyboard_focus.on_key_down(
                key,
                ctrl_key=ctrl_key,
                meta_key=meta_key,
                shift_key=shift_key,
                alt_key=alt_key,
            )
            self.changed()

    def _enclosing_window(self, morph: Optional[Morph]) -> Optional[Morph]:
        curr = morph
        while curr is not None and curr is not self:
            if curr.owner is self:
                return curr
            curr = curr.owner
        return None

    def _activate_halo_handle(self, hid: str, px: float, py: float) -> None:
        if self.active_halo is None:
            return
        target = self.active_halo.target
        if hid == "delete":
            target.delete()
            self.active_halo = None
            self.status_message = f"Deleted {target.__class__.__name__}"
        elif hid == "inspect":
            self.open_inspector(target)
        elif hid == "browse":
            self.open_browser(target.__class__.__name__)
        elif hid == "move":
            win = self._enclosing_window(target)
            drag_t = win if (win is not None and target.owner is not self) else target
            self.hand.drag_target = drag_t
            self.hand.drag_mode = "move"
        elif hid == "resize":
            win = self._enclosing_window(target)
            drag_t = win if (win is not None and target.owner is not self) else target
            self.active_halo.target = drag_t
            self.hand.drag_target = drag_t
            self.hand.drag_mode = "resize"
        elif hid == "duplicate":
            clone = target.duplicate()
            self.add_morph(clone)
            self.active_halo = HaloMorph(clone)
            self.status_message = f"Duplicated {clone.__class__.__name__}"
        elif hid == "color":
            target.cycle_color()

    def _execute_menubar_action(self, action_id: str) -> None:
        if action_id == "objectpond":
            self._open_world_menu(10, self.MENUBAR_HEIGHT + 4)
        elif action_id == "browser":
            self.open_browser()
        elif action_id == "workspace":
            self.open_workspace()
        elif action_id == "inspector":
            self.open_inspector(self)
        elif action_id == "transcript":
            self.open_transcript()
        elif action_id == "changes":
            self.open_changes()
        elif action_id == "bouncing":
            self.spawn_bouncing_atoms()
        elif action_id == "paint":
            self.spawn_bitblt_paint()
        elif action_id == "save_image":
            self.status_message = "Saving live image snapshot..."
            self.trigger_host_action("save_image")
        elif action_id == "export_image":
            self.status_message = "Exporting .image file..."
            self.trigger_host_action("export_image")
        elif action_id == "load_image":
            self.status_message = "Select a .image file to load..."
            self.trigger_host_action("load_image")
        elif action_id == "import_object":
            self.status_message = "Select a .image file to import an object from..."
            self.trigger_host_action("import_object")

    def open_modal(self, modal: Morph) -> Morph:
        modal.owner = self
        nx = max(12.0, (self.width - modal.width) / 2.0)
        ny = max(self.MENUBAR_HEIGHT + 12.0, (self.height - modal.height) / 2.0)
        dx = nx - modal.x
        dy = ny - modal.y
        if dx != 0.0 or dy != 0.0:
            modal.move_by(dx, dy)
        self.active_modal = modal
        if getattr(modal, "input_field", None) is not None:
            self.hand.keyboard_focus = modal.input_field
        else:
            self.hand.keyboard_focus = modal
        self.changed()
        return modal

    def close_modal(self) -> None:
        self.active_modal = None
        self.hand.pressed_morph = None
        self.changed()

    def _open_world_menu(self, x: float, y: float) -> None:
        from .widgets import MenuMorph

        items = [
            ("Open System Browser", lambda: self.open_browser()),
            ("Open Workspace", lambda: self.open_workspace()),
            ("Inspect World", lambda: self.open_inspector(self)),
            ("Inspect Smalltalk Dictionary", lambda: self.open_inspector(self.smalltalk)),
            ("Open Transcript", lambda: self.open_transcript()),
            ("Open Changes Log Viewer", lambda: self.open_changes()),
            ("Open App Builder", lambda: self.open_app_builder()),
            ("Open Sound Studio", lambda: self.open_sound_studio()),
            ("New Bouncing Atoms Morph", lambda: self.spawn_bouncing_atoms()),
            ("New BitBlt Paint Morph", lambda: self.spawn_bitblt_paint()),
            ("Open Widget Showcase", lambda: self.spawn_widget_showcase()),
            ("Save Live Image (IndexedDB + Server)", lambda: self.trigger_host_action("save_image")),
            ("Download .image File", lambda: self.trigger_host_action("export_image")),
        ]
        self.active_menu = MenuMorph(x, y, items)

    # --- Tool Window Spawners ---
    def _resolve_class(self, class_name: str, fallback: Any) -> Any:
        if self.smalltalk is not None:
            cls_obj = self.smalltalk.get_class(class_name)
            if cls_obj is not None:
                return cls_obj
        return fallback

    def open_browser(self, initial_class: Optional[str] = None) -> Optional[Morph]:
        from objectpond.tools.browser import SystemBrowserWindow

        cls = self._resolve_class("SystemBrowserWindow", SystemBrowserWindow)
        win = cls(self, initial_class=initial_class)
        self.add_morph(win)
        return win

    def open_workspace(self, initial_text: Optional[str] = None) -> Optional[Morph]:
        from objectpond.tools.workspace import WorkspaceWindow

        cls = self._resolve_class("WorkspaceWindow", WorkspaceWindow)
        win = cls(self, initial_text=initial_text)
        self.add_morph(win)
        return win

    def open_inspector(self, target_obj: Any) -> Optional[Morph]:
        from objectpond.tools.inspector import InspectorWindow

        cls = self._resolve_class("InspectorWindow", InspectorWindow)
        win = cls(self, target_obj)
        self.add_morph(win)
        return win

    def open_transcript(self) -> Optional[Morph]:
        from objectpond.tools.transcript import TranscriptWindow

        cls = self._resolve_class("TranscriptWindow", TranscriptWindow)
        win = cls(self)
        self.add_morph(win)
        return win

    def open_changes(self) -> Optional[Morph]:
        from objectpond.tools.transcript import ChangesViewerWindow

        cls = self._resolve_class("ChangesViewerWindow", ChangesViewerWindow)
        win = cls(self)
        self.add_morph(win)
        return win

    def open_debugger(self, exc_record_or_id: Any = None) -> Optional[Morph]:
        from objectpond.tools.debugger import DebuggerWindow

        exc_record = exc_record_or_id
        if isinstance(exc_record_or_id, int) and self.smalltalk is not None:
            exc_record = self.smalltalk.get_exception(exc_record_or_id)
        cls = self._resolve_class("DebuggerWindow", DebuggerWindow)
        win = cls(self, exc_record=exc_record)
        self.add_morph(win)
        return win

    def open_image_object_importer(
        self,
        image_bytes: bytes,
        filename: str = "objectpond.image",
    ) -> Optional[Morph]:
        from objectpond.tools.importer import ImageObjectImporterWindow

        cls = self._resolve_class("ImageObjectImporterWindow", ImageObjectImporterWindow)
        win = cls(self, image_bytes=image_bytes, filename=filename)
        self.add_morph(win)
        return win

    def spawn_bouncing_atoms(self) -> Optional[Morph]:
        from objectpond.tools.demos import BouncingAtomsMorph

        cls = self._resolve_class("BouncingAtomsMorph", BouncingAtomsMorph)
        atoms = cls(x=680, y=380, width=320, height=220)
        self.add_morph(atoms)
        return atoms

    def spawn_bitblt_paint(self) -> Optional[Morph]:
        from objectpond.tools.demos import BitBltPaintMorph

        cls = self._resolve_class("BitBltPaintMorph", BitBltPaintMorph)
        paint = cls(x=680, y=100, width=280, height=240)
        self.add_morph(paint)
        return paint

    def spawn_widget_showcase(self) -> Optional[Morph]:
        from objectpond.tools.demos import WidgetShowcaseWindow

        cls = self._resolve_class("WidgetShowcaseWindow", WidgetShowcaseWindow)
        win = cls(self)
        self.add_morph(win)
        return win

    def open_app_builder(self) -> Optional[Morph]:
        from objectpond.tools.app_builder import AppBuilderWindow

        cls = self._resolve_class("AppBuilderWindow", AppBuilderWindow)
        win = cls(self)
        self.add_morph(win)
        return win

    def open_sound_studio(self) -> Optional[Morph]:
        from objectpond.tools.demos import SoundStudioWindow

        cls = self._resolve_class("SoundStudioWindow", SoundStudioWindow)
        win = cls(self)
        self.add_morph(win)
        return win
