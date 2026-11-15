from .browser import SystemBrowserWindow
from .workspace import WorkspaceWindow
from .inspector import InspectorWindow
from .transcript import TranscriptWindow, ChangesViewerWindow
from .app_builder import AppBuilderWindow
from .demos import BouncingAtomsMorph, BitBltPaintMorph, WidgetShowcaseWindow, SoundStudioWindow

__all__ = [
    "SystemBrowserWindow",
    "WorkspaceWindow",
    "InspectorWindow",
    "TranscriptWindow",
    "ChangesViewerWindow",
    "AppBuilderWindow",
    "BouncingAtomsMorph",
    "BitBltPaintMorph",
    "WidgetShowcaseWindow",
    "SoundStudioWindow",
]
