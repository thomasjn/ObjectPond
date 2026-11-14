import copy
from typing import Any, List, Optional, Tuple
from .canvas import DisplayCanvas


class Morph:
    """
    Base graphical object in ObjectPond's Morphic environment.
    Every visual element—from the World desktop to windows, buttons, editors, and user
    simulations—is a live instance of Morph or a subclass.
    """

    PALETTE = [
        "#4a6fa5",
        "#478978",
        "#b56576",
        "#e56b6f",
        "#6d597a",
        "#d4a373",
        "#3a86ff",
        "#2a9d8f",
    ]

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 100,
        height: float = 80,
        color: str = "#3b4252",
        border_color: str = "#616e88",
        border_width: float = 1.0,
    ):
        self.x = float(x)
        self.y = float(y)
        self.width = float(width)
        self.height = float(height)
        self.color = color
        self.border_color = border_color
        self.border_width = float(border_width)
        self.corner_radius = 4.0
        self.visible = True
        self.clip_submorphs = False
        self.owner: Optional["Morph"] = None
        self.submorphs: List["Morph"] = []
        self.is_damaged = True

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)

    def set_bounds(self, x: float, y: float, w: float, h: float) -> None:
        dx = x - self.x
        dy = y - self.y
        if dx != 0 or dy != 0:
            self.move_by(dx, dy)
        self.set_extent(w, h)

    def move_by(self, dx: float, dy: float) -> None:
        if dx == 0 and dy == 0:
            return
        self.x += dx
        self.y += dy
        for sub in self.submorphs:
            sub.move_by(dx, dy)
        self.changed()

    def set_position(self, x: float, y: float) -> None:
        self.move_by(x - self.x, y - self.y)

    def set_extent(self, w: float, h: float) -> None:
        self.width = max(16.0, float(w))
        self.height = max(16.0, float(h))
        self.layout_submorphs()
        self.changed()

    def layout_submorphs(self) -> None:
        """Hook for composite morphs (like windows) to reflow child morphs on resize."""
        pass

    def contains_point(self, px: float, py: float) -> bool:
        return (
            self.visible
            and self.x <= px <= self.x + self.width
            and self.y <= py <= self.y + self.height
        )

    def add_morph(self, morph: "Morph") -> "Morph":
        if morph.owner is not None and morph.owner is not self:
            morph.owner.remove_morph(morph)
        if morph in self.submorphs:
            self.submorphs.remove(morph)
        morph.owner = self
        self.submorphs.append(morph)
        self.changed()
        return morph

    def add_morph_front(self, morph: "Morph") -> "Morph":
        return self.add_morph(morph)

    def remove_morph(self, morph: "Morph") -> None:
        if morph in self.submorphs:
            self.submorphs.remove(morph)
            morph.owner = None
            self.changed()

    def delete(self) -> None:
        if self.owner is not None:
            self.owner.remove_morph(self)

    def bring_to_front(self) -> None:
        if self.owner is not None and self in self.owner.submorphs:
            self.owner.submorphs.remove(self)
            self.owner.submorphs.append(self)
            self.owner.changed()

    def world(self) -> Optional[Any]:
        curr: Optional[Morph] = self
        while curr is not None:
            if curr.__class__.__name__ == "WorldMorph":
                return curr
            curr = curr.owner
        return None

    def changed(self) -> None:
        self.is_damaged = True
        w = self.world()
        if w is not None and w is not self:
            w.is_damaged = True

    def morph_at(self, px: float, py: float) -> Optional["Morph"]:
        if not self.visible:
            return None
        if self.clip_submorphs and not self.contains_point(px, py):
            return None
        for sub in reversed(self.submorphs):
            if sub.visible:
                hit = sub.morph_at(px, py)
                if hit is not None:
                    return hit
        if self.contains_point(px, py):
            return self
        return None

    def draw_on(self, canvas: DisplayCanvas) -> None:
        if self.corner_radius > 0:
            canvas.fill_round_rect(
                self.x,
                self.y,
                self.width,
                self.height,
                self.corner_radius,
                self.color,
                self.border_color if self.border_width > 0 else None,
                self.border_width,
            )
        else:
            canvas.fill_rect(self.x, self.y, self.width, self.height, self.color)
            if self.border_width > 0:
                canvas.stroke_rect(
                    self.x, self.y, self.width, self.height, self.border_color, self.border_width
                )
        # If this morph carries a Form bitmap (`self.bitmap`), blit it automatically
        bmp = getattr(self, "bitmap", None)
        if bmp is not None and hasattr(bmp, "to_bytes"):
            canvas.blit_form(bmp, self.x + 2, self.y + 2)

    def full_draw_on(self, canvas: DisplayCanvas) -> None:
        if not self.visible:
            return
        self.draw_on(canvas)
        if self.clip_submorphs:
            canvas.push_clip(self.x, self.y, self.width, self.height)
        try:
            for sub in self.submorphs:
                if sub.visible:
                    sub.full_draw_on(canvas)
        finally:
            if self.clip_submorphs:
                canvas.pop_clip()

    # --- Live Stepping Protocol ---
    def wants_steps(self) -> bool:
        return False

    def step(self) -> None:
        pass

    def all_morphs(self) -> List["Morph"]:
        result = [self]
        for sub in list(self.submorphs):
            result.extend(sub.all_morphs())
        return result

    # --- Event Handling Protocol ---
    def handles_mouse_down(self, px: float, py: float, button: int) -> bool:
        return True

    def on_mouse_down(self, px: float, py: float, button: int) -> None:
        # Default behavior: bring enclosing window to front and allow dragging top-level morphs
        pass

    def on_mouse_move(self, px: float, py: float, dx: float, dy: float) -> None:
        pass

    def on_mouse_up(self, px: float, py: float, button: int) -> None:
        pass

    def on_mouse_wheel(self, px: float, py: float, delta_y: float) -> None:
        if self.owner is not None:
            self.owner.on_mouse_wheel(px, py, delta_y)

    def on_key_down(
        self,
        key: str,
        ctrl_key: bool = False,
        meta_key: bool = False,
        shift_key: bool = False,
        alt_key: bool = False,
    ) -> None:
        pass

    def on_paste(self, text: str) -> None:
        pass

    def cycle_color(self) -> None:
        try:
            idx = (self.PALETTE.index(self.color) + 1) % len(self.PALETTE)
        except ValueError:
            idx = 0
        self.color = self.PALETTE[idx]
        self.changed()

    def duplicate(self) -> "Morph":
        memo = {id(self.owner): None, id(self.world()): None}
        cloned = copy.deepcopy(self, memo)
        cloned.owner = None
        cloned.move_by(24, 24)
        return cloned

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} ({int(self.x)}, {int(self.y)}, {int(self.width)}x{int(self.height)})>"
