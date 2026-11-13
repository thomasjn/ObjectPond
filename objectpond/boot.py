from typing import Tuple
from objectpond.kernel.object_memory import SystemDictionary, ChangesLog
from objectpond.morphic.canvas import Form
from objectpond.morphic.morph import Morph
from objectpond.morphic.world import WorldMorph, HandMorph, HaloMorph
from objectpond.morphic.widgets import (
    SystemWindowMorph,
    ButtonMorph,
    ListMorph,
    CodeEditorMorph,
    MenuMorph,
    LabelMorph,
)
from objectpond.tools.browser import SystemBrowserWindow
from objectpond.tools.workspace import WorkspaceWindow
from objectpond.tools.inspector import InspectorWindow
from objectpond.tools.transcript import TranscriptWindow, ChangesViewerWindow
from objectpond.tools.debugger import DebuggerWindow
from objectpond.tools.demos import BouncingAtomsMorph, BitBltPaintMorph


def create_default_environment(
    width: float = 1280, height: float = 800
) -> Tuple[SystemDictionary, WorldMorph]:
    """
    Initializes a full ObjectPond runtime environment:
    - Sets up ChangesLog and Smalltalk SystemDictionary
    - Registers all Morphic core classes, widgets, development tools, and demo simulations
    - Spawns the root WorldMorph desktop
    - Opens the default desktop tools (System Browser, Workspace, Transcript, Bouncing Atoms)
    """
    changes_log = ChangesLog()
    smalltalk = SystemDictionary(changes_log=changes_log)

    # Register all system classes in appropriate categories
    class_registry = [
        ("Morphic-Core", Form),
        ("Morphic-Core", Morph),
        ("Morphic-Core", WorldMorph),
        ("Morphic-Core", HandMorph),
        ("Morphic-Core", HaloMorph),
        ("Morphic-Widgets", SystemWindowMorph),
        ("Morphic-Widgets", ButtonMorph),
        ("Morphic-Widgets", ListMorph),
        ("Morphic-Widgets", CodeEditorMorph),
        ("Morphic-Widgets", MenuMorph),
        ("Morphic-Widgets", LabelMorph),
        ("Tools-Browser", SystemBrowserWindow),
        ("Tools-Workspace", WorkspaceWindow),
        ("Tools-Inspector", InspectorWindow),
        ("Tools-Transcript", TranscriptWindow),
        ("Tools-Transcript", ChangesViewerWindow),
        ("Tools-Debugger", DebuggerWindow),
        ("User-Objects", BouncingAtomsMorph),
        ("User-Objects", BitBltPaintMorph),
    ]
    for category, cls_obj in class_registry:
        smalltalk.register_class(category, cls_obj)

    # Create root desktop WorldMorph
    world = WorldMorph(width=width, height=height, smalltalk=smalltalk)

    # Populate default desktop tools
    browser = SystemBrowserWindow(
        world,
        initial_class="BouncingAtomsMorph",
        x=30,
        y=42,
        width=min(630.0, width * 0.50),
        height=min(420.0, height * 0.55),
    )
    workspace = WorkspaceWindow(
        world,
        x=min(670.0, width * 0.52),
        y=42,
        width=min(530.0, width * 0.44),
        height=min(340.0, height * 0.45),
    )
    transcript = TranscriptWindow(
        world,
        x=min(670.0, width * 0.52),
        y=min(400.0, height * 0.52),
        width=min(530.0, width * 0.44),
        height=min(220.0, height * 0.30),
    )
    atoms = BouncingAtomsMorph(
        x=30,
        y=min(480.0, height * 0.62),
        width=min(320.0, width * 0.28),
        height=min(210.0, height * 0.28),
    )

    world.add_morph(browser)
    world.add_morph(workspace)
    world.add_morph(transcript)
    world.add_morph(atoms)

    smalltalk.log_transcript("ObjectPond 1.0 booted.")
    smalltalk.log_transcript("Welcome to ObjectPond — Live Python Morphic Environment!")
    smalltalk.log_transcript("Alt+Click any Morph to open Morphic Halos.")

    return smalltalk, world
