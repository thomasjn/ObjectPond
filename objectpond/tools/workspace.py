from typing import Any, Optional
from objectpond.morphic.widgets import SystemWindowMorph, ButtonMorph, CodeEditorMorph


DEFAULT_WORKSPACE_CODE = '''# ObjectPond Interactive Workspace
# Select any expression (or place the cursor on a single line) and press:
#   Cmd+D (Do it) | Cmd+P (Print it) | Cmd+I (Inspect it)

Transcript.show("Hello from ObjectPond!")

# Spawn a parameterized BouncingAtomsMorph (select both lines and press Cmd+D):
# atoms = BouncingAtomsMorph(x=400, y=200, width=360, height=260, num_atoms=30)
# World.add_morph(atoms)

# Mutate the live BouncingAtomsMorph instance directly from the Workspace:
# atoms.color = "#112233"
# atoms.border_color = "#ebcb8b"
# for a in atoms.atoms: a["vx"] *= 2.0; a["vy"] *= 2.0; a["radius"] = 8.0

# Create and add a basic Morph to the World:
# m = Morph(x=200, y=150, width=120, height=80, color="#b56576")
# World.add_morph(m)
# m.cycle_color()

# Inspect the World desktop or Smalltalk SystemDictionary (place cursor on line + Cmd+I):
# World
# Smalltalk

# Try an evaluation:
6 * 7
'''


class WorkspaceWindow(SystemWindowMorph):
    """
    Classic Smalltalk Workspace scratchpad.
    Provides interactive evaluation with Do it, Print it, Inspect it, and Clear buttons.
    """

    def __init__(
        self,
        world: Any,
        initial_text: Optional[str] = None,
        x: float = 80,
        y: float = 70,
        width: float = 540,
        height: float = 360,
    ):
        super().__init__(
            title="Workspace",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b536e",
        )
        ctx = getattr(world, "workspace_globals", {})

        # Toolbar buttons
        self.do_it_btn = ButtonMorph(
            "Do it (Cmd+D)",
            x=x + 4,
            y=y + 30,
            width=110,
            height=24,
            on_click=self.on_do_it,
        )
        self.print_it_btn = ButtonMorph(
            "Print it (Cmd+P)",
            x=x + 120,
            y=y + 30,
            width=125,
            height=24,
            on_click=self.on_print_it,
        )
        self.inspect_it_btn = ButtonMorph(
            "Inspect it (Cmd+I)",
            x=x + 251,
            y=y + 30,
            width=140,
            height=24,
            on_click=self.on_inspect_it,
        )
        self.clear_btn = ButtonMorph(
            "Clear",
            x=x + 397,
            y=y + 30,
            width=65,
            height=24,
            on_click=self.on_clear,
        )

        code_text = DEFAULT_WORKSPACE_CODE if initial_text is None else initial_text
        self.editor = CodeEditorMorph(
            x=x + 4,
            y=y + 58,
            width=width - 8,
            height=height - 64,
            text=code_text,
            context=ctx,
        )

        self.add_morph(self.do_it_btn)
        self.add_morph(self.print_it_btn)
        self.add_morph(self.inspect_it_btn)
        self.add_morph(self.clear_btn)
        self.add_morph(self.editor)

        self.layout_submorphs()

    def on_do_it(self) -> Any:
        return self.editor.do_it()

    def on_print_it(self) -> str:
        return self.editor.print_it()

    def on_inspect_it(self) -> Any:
        return self.editor.inspect_it()

    def on_clear(self) -> None:
        self.editor.set_text("")

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "do_it_btn"):
            return

        bx = self.x + 4.0
        by = self.y + self.TITLEBAR_HEIGHT + 4.0
        for btn in [self.do_it_btn, self.print_it_btn, self.inspect_it_btn, self.clear_btn]:
            btn.set_position(bx, by)
            bx += btn.width + 6.0

        ey = by + 28.0
        ew = max(100.0, self.width - 8.0)
        eh = max(40.0, self.y + self.height - ey - 4.0)
        self.editor.set_bounds(self.x + 4.0, ey, ew, eh)
