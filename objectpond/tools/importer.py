import json
from typing import Any, Dict, List, Optional
from objectpond.kernel.image import ImageSerializer
from objectpond.morphic.morph import Morph
from objectpond.morphic.widgets import (
    ButtonMorph,
    CodeEditorMorph,
    ListMorph,
    SystemWindowMorph,
)


class ImageObjectImporterWindow(SystemWindowMorph):
    """
    Allows browsing objects inside a saved `.image` snapshot file on disk
    and importing a selected object (along with its class/methods) into the live World.
    """

    def __init__(
        self,
        world: Any,
        image_bytes: bytes,
        filename: str = "objectpond.image",
        x: float = 220,
        y: float = 110,
        width: float = 640,
        height: float = 420,
    ):
        super().__init__(
            title=f"Import Object from {filename}",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#2e4d46",
        )
        self._world_ref = world
        self.filename = filename
        self.snapshot: Dict[str, Any] = ImageSerializer.parse_image_bytes(image_bytes)
        self.candidates: List[Dict[str, Any]] = ImageSerializer.list_importable_objects(self.snapshot)
        self.selected_idx: int = -1

        self.import_btn = ButtonMorph(
            "Import Selected",
            x=x + 4,
            y=y + 30,
            width=136,
            height=24,
            on_click=self.on_import_clicked,
            color="#2d4f3e",
        )
        self.object_list = ListMorph(
            x=x + 4,
            y=y + 58,
            width=260,
            height=height - 62,
            on_select=self.on_object_selected,
        )
        self.detail_editor = CodeEditorMorph(
            x=x + 268,
            y=y + 58,
            width=width - 272,
            height=height - 62,
            text="# Select an object on the left to inspect and import.",
        )

        self.add_morph(self.import_btn)
        self.add_morph(self.object_list)
        self.add_morph(self.detail_editor)

        self.object_list.set_items([c["label"] for c in self.candidates] or ["<no objects found>"])
        self.layout_submorphs()
        if self.candidates:
            self.object_list.select_index(0, notify=True)

    def _world(self) -> Any:
        return self.world() or getattr(self, "_world_ref", None)

    def on_object_selected(self, idx: int, _label: str) -> None:
        if not (0 <= idx < len(self.candidates)):
            self.selected_idx = -1
            return
        self.selected_idx = idx
        item = self.candidates[idx]
        entry = item["entry"]
        preview = {
            "id": item["id"],
            "class": item["class"],
            "state": entry.get("state", {}),
        }
        if "form" in entry:
            preview["form"] = {
                "width": entry["form"].get("width"),
                "height": entry["form"].get("height"),
            }
        self.detail_editor.set_text(json.dumps(preview, indent=2, default=str))

    def on_import_clicked(self) -> Any:
        if not (0 <= self.selected_idx < len(self.candidates)):
            return None
        item = self.candidates[self.selected_idx]
        w = self._world()
        st = getattr(w, "smalltalk", None) if w else None
        if w is None or st is None:
            return None

        serializer = ImageSerializer(st)
        obj = serializer.import_object_from_snapshot(self.snapshot, item["id"], target_world=w)
        if isinstance(obj, Morph):
            obj.bring_to_front()
        else:
            gname = f"imported_{item['class'].lower()}"
            w.workspace_globals[gname] = obj
            w.open_inspector(obj)
        w.status_message = f"Imported {item['class']} from {self.filename}"
        w.changed()
        return obj

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "object_list"):
            return
        cx = self.x + 4.0
        cy = self.y + self.TITLEBAR_HEIGHT + 4.0
        cw = max(140.0, self.width - 8.0)
        ch = max(120.0, self.height - self.TITLEBAR_HEIGHT - 8.0)

        self.import_btn.set_position(cx, cy)
        list_y = cy + 28.0
        list_h = max(40.0, ch - 28.0)
        list_w = max(120.0, min(280.0, cw * 0.44))
        self.object_list.set_bounds(cx, list_y, list_w, list_h)
        self.detail_editor.set_bounds(cx + list_w + 4.0, list_y, max(60.0, cw - list_w - 4.0), list_h)
