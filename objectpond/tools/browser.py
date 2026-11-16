import ast
from typing import Any, List, Optional
from objectpond.morphic.widgets import SystemWindowMorph, ListMorph, CodeEditorMorph, ButtonMorph


class SystemBrowserWindow(SystemWindowMorph):
    """
    Classic Smalltalk 4-pane System Browser in ObjectPond:
    - Top 4 panes: Categories | Classes | Protocols | Methods
    - Toolbar: Accept / Compile | + New Class | + New Method | Inspect Class
    - Bottom pane: CodeEditorMorph showing live method source or class definition
    """

    def __init__(
        self,
        world: Any,
        initial_class: Optional[str] = None,
        x: float = 40,
        y: float = 45,
        width: float = 640,
        height: float = 430,
    ):
        super().__init__(
            title="System Browser",
            x=x,
            y=y,
            width=width,
            height=height,
            header_color="#3b536e",
        )
        self.base_title: str = self.title
        self._smalltalk = getattr(world, "smalltalk", None)
        self.selected_category: Optional[str] = None
        self.selected_class_name: Optional[str] = None
        self.selected_protocol: Optional[str] = None
        self.selected_method_name: Optional[str] = None

        # 4 Top Panes
        self.category_list = ListMorph(
            x=x + 4,
            y=y + 30,
            width=150,
            height=130,
            on_select=self._on_category_selected,
        )
        self.class_list = ListMorph(
            x=x + 158,
            y=y + 30,
            width=150,
            height=130,
            on_select=self._on_class_selected,
        )
        self.protocol_list = ListMorph(
            x=x + 312,
            y=y + 30,
            width=150,
            height=130,
            on_select=self._on_protocol_selected,
        )
        self.method_list = ListMorph(
            x=x + 466,
            y=y + 30,
            width=150,
            height=130,
            on_select=self._on_method_selected,
        )

        # Action Buttons
        self.accept_btn = ButtonMorph(
            "Accept (Cmd+S)",
            x=x + 4,
            y=y + 164,
            width=112,
            height=24,
            on_click=self.on_accept_clicked,
            color="#2d4f3e",
        )
        self.new_class_btn = ButtonMorph(
            "+ New Class",
            x=x + 121,
            y=y + 164,
            width=88,
            height=24,
            on_click=self.on_new_class_clicked,
        )
        self.new_method_btn = ButtonMorph(
            "+ New Method",
            x=x + 214,
            y=y + 164,
            width=96,
            height=24,
            on_click=self.on_new_method_clicked,
        )
        self.inspect_class_btn = ButtonMorph(
            "Inspect Class",
            x=x + 315,
            y=y + 164,
            width=94,
            height=24,
            on_click=self.on_inspect_class_clicked,
        )
        self.instantiate_btn = ButtonMorph(
            "+ Instance",
            x=x + 414,
            y=y + 164,
            width=90,
            height=24,
            on_click=self.on_instantiate_clicked,
            color="#3b5e7a",
        )
        self.delete_class_btn = ButtonMorph(
            "Delete Class",
            x=x + 509,
            y=y + 164,
            width=94,
            height=24,
            on_click=self.on_delete_class_clicked,
            color="#b02a37",
        )

        # Bottom Code Editor
        ctx = getattr(world, "workspace_globals", {})
        self.editor = CodeEditorMorph(
            x=x + 4,
            y=y + 192,
            width=width - 8,
            height=height - 198,
            context=ctx,
            on_accept=self.accept_editor,
        )

        # Add all submorphs
        self.add_morph(self.category_list)
        self.add_morph(self.class_list)
        self.add_morph(self.protocol_list)
        self.add_morph(self.method_list)
        self.add_morph(self.accept_btn)
        self.add_morph(self.new_class_btn)
        self.add_morph(self.new_method_btn)
        self.add_morph(self.inspect_class_btn)
        self.add_morph(self.instantiate_btn)
        self.add_morph(self.delete_class_btn)
        self.add_morph(self.editor)

        # Layout and populate data
        self.layout_submorphs()
        self.refresh_categories()

        if initial_class:
            found_cat = None
            if self.smalltalk:
                rec = self.smalltalk.get_class_record(initial_class)
                if rec:
                    found_cat = rec.category
                else:
                    for cat, classes in self.smalltalk.categories.items():
                        if initial_class in classes:
                            found_cat = cat
                            break
            if found_cat:
                self.select_category(found_cat)
            self.select_class(initial_class)
        elif self.category_list.items:
            self.select_category(self.category_list.items[0])

    @property
    def smalltalk(self) -> Optional[Any]:
        if self._smalltalk is not None:
            return self._smalltalk
        w = self.world()
        if w is not None and getattr(w, "smalltalk", None) is not None:
            return w.smalltalk
        return None

    @smalltalk.setter
    def smalltalk(self, val: Any) -> None:
        self._smalltalk = val

    def refresh_categories(self) -> None:
        cats = self.smalltalk.get_categories() if self.smalltalk else []
        self.category_list.set_items(cats, keep_selection=True)

    def refresh_protocols(self) -> None:
        if self.selected_class_name and self.smalltalk:
            protocols = self.smalltalk.get_protocols(self.selected_class_name)
            self.protocol_list.set_items(protocols, keep_selection=True)

    def refresh_methods(self) -> None:
        if self.selected_class_name and self.smalltalk:
            methods = self.smalltalk.get_methods(
                self.selected_class_name, self.selected_protocol or "all"
            )
            self.method_list.set_items(methods, keep_selection=True)

    def _on_category_selected(self, idx: int, category: str) -> None:
        self.select_category(category)

    def _on_class_selected(self, idx: int, cls_name: str) -> None:
        self.select_class(cls_name)

    def _on_protocol_selected(self, idx: int, proto: str) -> None:
        self.select_protocol(proto)

    def _on_method_selected(self, idx: int, method_name: str) -> None:
        self.select_method(method_name)

    def on_accept_clicked(self) -> Any:
        return self.accept_editor()

    def on_new_class_clicked(self) -> None:
        cat = self.selected_category or "User-Objects"
        template = (
            f"# Define new class in category '{cat}'\n"
            f"class MyCustomMorph(Morph):\n"
            f"    def __init__(self, x=100, y=100, width=120, height=80):\n"
            f"        super().__init__(x, y, width, height)\n"
            f"        self.color = '#4a6fa5'\n"
        )
        self.selected_method_name = None
        self.method_list.select_index(-1, notify=False)
        self.editor.set_text(template)

    def on_new_method_clicked(self) -> None:
        cls_name = self.selected_class_name or "Morph"
        proto = self.selected_protocol if self.selected_protocol and self.selected_protocol != "all" else "operations"
        template = (
            f"def new_method(self):\n"
            f"    \"\"\"{proto} method on {cls_name}\"\"\"\n"
            f"    pass\n"
        )
        self.selected_method_name = None
        self.method_list.select_index(-1, notify=False)
        self.editor.set_text(template)

    def on_inspect_class_clicked(self) -> None:
        if self.selected_class_name and self.smalltalk:
            cls_obj = self.smalltalk.get_class(self.selected_class_name)
            if cls_obj is not None:
                w = self.world()
                if w is not None:
                    w.open_inspector(cls_obj)

    def on_instantiate_clicked(self) -> Optional[Any]:
        if not (self.selected_class_name and self.smalltalk):
            return None
        cls_name = self.selected_class_name
        cls_obj = self.smalltalk.get_class(cls_name)
        w = self.world()
        if cls_obj is None or w is None:
            return None
        try:
            try:
                inst = cls_obj()
            except TypeError:
                inst = cls_obj(w)
            from objectpond.morphic.morph import Morph

            if isinstance(inst, Morph):
                if inst.x == 0 and inst.y == 0:
                    inst.set_position(min(w.width - inst.width - 20.0, self.x + self.width + 20.0), max(40.0, self.y))
                w.add_morph(inst)
                w.status_message = f"Spawned {cls_name} instance"
            else:
                w.open_inspector(inst)
                w.status_message = f"Instantiated {cls_name}"
            w.changed()
            return inst
        except Exception as exc:
            w.status_message = f"Instantiate error: {exc}"
            self.smalltalk.log_transcript(f"Instantiate Error ({cls_name}): {exc}")
            return None

    def on_delete_class_clicked(self) -> None:
        if not (self.selected_class_name and self.smalltalk):
            return
        cls_name = self.selected_class_name
        w = self.world()
        if w is None:
            return
        if cls_name in ("Morph", "WorldMorph", "HandMorph", "HaloMorph", "SystemWindowMorph"):
            w.status_message = f"Cannot delete core kernel class '{cls_name}'"
            return
        from objectpond.morphic.app_widgets import DialogMorph

        dlg = DialogMorph(
            title=f"Delete {cls_name}?",
            message=f"Delete class '{cls_name}' and all running instances? Are you sure?",
            buttons=[
                ("Delete", lambda: self._confirm_delete_class(cls_name)),
                ("Cancel", None),
            ],
            width=400,
            height=155,
        )
        w.open_modal(dlg)

    def _confirm_delete_class(self, cls_name: str) -> None:
        w = self.world()
        if not self.smalltalk:
            return
        try:
            removed = self.smalltalk.delete_class(cls_name, world=w)
            self.selected_class_name = None
            self.selected_method_name = None
            self.refresh_categories()
            if self.selected_category in self.category_list.items:
                self.select_category(self.selected_category)
            elif self.category_list.items:
                self.select_category(self.category_list.items[0])
            else:
                self.select_category(None)
            if w is not None:
                w.status_message = f"Deleted {cls_name} ({removed} instances removed)"
                w.changed()
        except Exception as exc:
            if w is not None:
                w.status_message = f"Delete failed: {exc}"

    def select_category(self, cat: Optional[str]) -> None:
        self.selected_category = cat
        if cat is not None:
            self.category_list.select_value(cat, notify=False)
            classes = self.smalltalk.get_classes_in_category(cat) if self.smalltalk else []
            self.class_list.set_items(classes)
            if self.selected_class_name in classes:
                self.select_class(self.selected_class_name)
            elif classes:
                self.select_class(classes[0])
            else:
                self.select_class(None)
        else:
            self.category_list.select_index(-1, notify=False)
            self.class_list.set_items([])
            self.select_class(None)

    def select_class(self, cls_name: Optional[str]) -> None:
        self.selected_class_name = cls_name
        base = getattr(self, "base_title", "System Browser")
        if cls_name is not None and self.smalltalk is not None:
            self.class_list.select_value(cls_name, notify=False)
            self.title = f"{base}: {cls_name}"
            protocols = self.smalltalk.get_protocols(cls_name)
            self.protocol_list.set_items(protocols)
            if "all" in protocols:
                self.select_protocol("all")
            elif protocols:
                self.select_protocol(protocols[0])
            else:
                self.select_protocol(None)
        else:
            self.class_list.select_index(-1, notify=False)
            self.title = base
            self.protocol_list.set_items([])
            self.select_protocol(None)

    def select_protocol(self, proto: Optional[str]) -> None:
        self.selected_protocol = proto
        if proto is not None and self.selected_class_name and self.smalltalk:
            self.protocol_list.select_value(proto, notify=False)
            methods = self.smalltalk.get_methods(self.selected_class_name, proto)
            self.method_list.set_items(methods)
            if self.selected_method_name and self.selected_method_name in methods:
                self.select_method(self.selected_method_name)
            else:
                self.selected_method_name = None
                self.method_list.select_index(-1, notify=False)
                cls_src = self.smalltalk.get_class_definition_source(self.selected_class_name)
                self.editor.set_text(cls_src)
        else:
            self.protocol_list.select_index(-1, notify=False)
            self.method_list.set_items([])
            self.selected_method_name = None
            self.editor.set_text("")

    def select_method(self, method_name: Optional[str]) -> None:
        self.selected_method_name = method_name
        if method_name is not None and self.selected_class_name and self.smalltalk:
            # Check if method is in current method list; if not, switch protocol to all
            if method_name not in self.method_list.items:
                protocols = self.smalltalk.get_protocols(self.selected_class_name)
                if "all" in protocols:
                    self.selected_protocol = "all"
                    self.protocol_list.select_value("all", notify=False)
                    self.method_list.set_items(
                        self.smalltalk.get_methods(self.selected_class_name, "all")
                    )
            self.method_list.select_value(method_name, notify=False)
            try:
                src = self.smalltalk.get_method_source(self.selected_class_name, method_name)
                self.editor.set_text(src)
            except Exception:
                pass
        else:
            self.method_list.select_index(-1, notify=False)
            if self.selected_class_name and self.smalltalk:
                cls_src = self.smalltalk.get_class_definition_source(self.selected_class_name)
                self.editor.set_text(cls_src)
            else:
                self.editor.set_text("")

    def accept_editor(self, src: Optional[str] = None) -> Any:
        if src is None:
            src = self.editor.text
        src_clean = src.strip()
        if not src_clean:
            return None

        lines = [
            line.strip()
            for line in src_clean.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        is_class_def = False
        if lines and lines[0].startswith("class "):
            is_class_def = True

        st = self.smalltalk
        if st is None:
            return None

        try:
            if is_class_def:
                category = self.selected_category or "User-Objects"
                new_cls = st.define_class(category, src)
                cls_name = new_cls.__name__
                self.refresh_categories()
                self.select_category(category)
                self.select_class(cls_name)
                w = self.world()
                if w is not None:
                    w.status_message = f"Defined class {cls_name} in {category}"
                return new_cls
            else:
                cls_name = self.selected_class_name
                if not cls_name:
                    raise ValueError("No class selected to compile method onto")
                protocol = self.selected_protocol
                if not protocol or protocol == "all":
                    protocol = "operations"
                method_name = st.compile_and_install_method(
                    class_name=cls_name,
                    method_name=self.selected_method_name,
                    source_code=src,
                    protocol=protocol,
                )
                self.refresh_protocols()
                self.refresh_methods()
                self.select_method(method_name)
                w = self.world()
                if w is not None:
                    w.status_message = f"Compiled {cls_name}>>{method_name}"
                return method_name
        except Exception as exc:
            w = self.world()
            if w is not None:
                w.status_message = f"Compile error: {exc}"
            if st is not None:
                st.log_transcript(f"Compile Error: {exc}")
            return exc

    def layout_submorphs(self) -> None:
        super().layout_submorphs()
        if not hasattr(self, "category_list"):
            return

        content_x = self.x + 4.0
        content_y = self.y + self.TITLEBAR_HEIGHT + 4.0
        content_w = max(100.0, self.width - 8.0)
        content_h = max(100.0, self.height - self.TITLEBAR_HEIGHT - 8.0)

        top_h = max(60.0, min(140.0, content_h * 0.36))
        pane_spacing = 3.0
        pane_w = max(20.0, (content_w - (3.0 * pane_spacing)) / 4.0)

        self.category_list.set_bounds(content_x, content_y, pane_w, top_h)
        self.class_list.set_bounds(content_x + pane_w + pane_spacing, content_y, pane_w, top_h)
        self.protocol_list.set_bounds(
            content_x + 2 * (pane_w + pane_spacing), content_y, pane_w, top_h
        )
        self.method_list.set_bounds(
            content_x + 3 * (pane_w + pane_spacing), content_y, pane_w, top_h
        )

        btn_y = content_y + top_h + 4.0
        btn_h = 24.0
        bx = content_x
        for btn in [
            self.accept_btn,
            self.new_class_btn,
            self.new_method_btn,
            self.inspect_class_btn,
            self.instantiate_btn,
            self.delete_class_btn,
        ]:
            btn.set_position(bx, btn_y)
            bx += btn.width + 5.0

        editor_y = btn_y + btn_h + 4.0
        editor_h = max(40.0, self.y + self.height - editor_y - 4.0)
        self.editor.set_bounds(content_x, editor_y, content_w, editor_h)
