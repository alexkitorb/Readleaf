#!/usr/bin/env python3
"""Readleaf — a focused RTF reader for GTK 4 desktops."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from rtf_parser import Document, TextStyle, parse_rtf  # noqa: E402


APP_ID = "io.github.readleaf.Reader"
MAX_FILE_SIZE = 40 * 1024 * 1024


CSS = """
window { background: @window_bg_color; }
.document-view {
  font-family: "Noto Serif", "DejaVu Serif", serif;
  font-size: 12pt;
  line-height: 1.5;
  padding: 40px 56px;
}
.document-frame {
  background: @view_bg_color;
  border-left: 1px solid alpha(@borders, .7);
  border-right: 1px solid alpha(@borders, .7);
}
.welcome-title { font-size: 24pt; font-weight: 700; }
.welcome-subtitle { font-size: 11pt; color: @insensitive_fg_color; }
.drop-card {
  border: 1px solid @borders;
  border-radius: 18px;
  background: alpha(@view_bg_color, .72);
  padding: 42px;
}
.status-bar {
  min-height: 30px;
  padding: 0 12px;
  color: @insensitive_fg_color;
  border-top: 1px solid @borders;
  font-size: 9pt;
}
.search-count { color: @insensitive_fg_color; min-width: 68px; }
"""


class ReaderWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Readleaf")
        self.set_default_size(920, 720)
        self.set_size_request(480, 360)
        self.current_file: Gio.File | None = None
        self.document: Document | None = None
        self.zoom = 1.0
        self.matches: list[tuple[int, int]] = []
        self.match_index = -1
        self._tag_cache: dict[TextStyle, Gtk.TextTag] = {}

        self._build_header()
        self._build_content()
        self._install_actions()
        self._install_drop_target()

    def _build_header(self) -> None:
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        open_button = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Open RTF (Ctrl+O)")
        open_button.connect("clicked", lambda _button: self.activate_action("open", None))
        header.pack_start(open_button)

        self.title_label = Gtk.Label(label="Readleaf")
        self.title_label.add_css_class("title")
        header.set_title_widget(self.title_label)

        self.search_button = Gtk.ToggleButton(icon_name="edit-find-symbolic", tooltip_text="Find (Ctrl+F)")
        self.search_button.set_sensitive(False)
        self.search_button.connect("toggled", self._toggle_search)
        header.pack_end(self.search_button)

        menu = Gio.Menu()
        menu.append("Zoom in", "win.zoom-in")
        menu.append("Zoom out", "win.zoom-out")
        menu.append("Actual size", "win.zoom-reset")
        menu.append("Document details", "win.details")
        menu.append("About Readleaf", "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Main menu")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

    def _build_content(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        self.search_bar = Gtk.SearchBar()
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_row.set_halign(Gtk.Align.CENTER)
        self.search_entry = Gtk.SearchEntry(placeholder_text="Find in document")
        self.search_entry.set_width_chars(28)
        self.search_entry.connect("search-changed", self._search_changed)
        self.search_entry.connect("next-match", lambda _entry: self._move_match(1))
        self.search_entry.connect("previous-match", lambda _entry: self._move_match(-1))
        search_row.append(self.search_entry)
        self.search_count = Gtk.Label(label="", xalign=0)
        self.search_count.add_css_class("search-count")
        search_row.append(self.search_count)
        previous = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous match (Shift+Enter)")
        previous.connect("clicked", lambda _button: self._move_match(-1))
        search_row.append(previous)
        following = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next match (Enter)")
        following.connect("clicked", lambda _button: self._move_match(1))
        search_row.append(following)
        close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Close search (Escape)")
        close.connect("clicked", lambda _button: self.search_button.set_active(False))
        search_row.append(close)
        self.search_bar.set_child(search_row)
        self.search_bar.connect_entry(self.search_entry)
        root.append(self.search_bar)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=180)
        self.stack.set_vexpand(True)
        root.append(self.stack)

        welcome = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        welcome.set_halign(Gtk.Align.CENTER)
        welcome.set_valign(Gtk.Align.CENTER)
        welcome.add_css_class("drop-card")
        icon = Gtk.Image.new_from_icon_name("x-office-document-symbolic")
        icon.set_pixel_size(64)
        welcome.append(icon)
        title = Gtk.Label(label="Open an RTF document")
        title.add_css_class("welcome-title")
        welcome.append(title)
        subtitle = Gtk.Label(label="Drop a .rtf file here, or choose one from your computer")
        subtitle.add_css_class("welcome-subtitle")
        welcome.append(subtitle)
        choose = Gtk.Button(label="Open document")
        choose.add_css_class("suggested-action")
        choose.set_halign(Gtk.Align.CENTER)
        choose.connect("clicked", lambda _button: self.activate_action("open", None))
        welcome.append(choose)
        self.stack.add_named(welcome, "welcome")

        reader_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_vexpand(True)
        scroller.add_css_class("document-frame")
        self.text_view = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=24,
            right_margin=24,
            top_margin=24,
            bottom_margin=40,
            pixels_above_lines=2,
            pixels_below_lines=2,
        )
        self.text_view.add_css_class("document-view")
        self.buffer = self.text_view.get_buffer()
        self.search_tag = self.buffer.create_tag("search-result", background="#f6d32d", foreground="#1f1f1f")
        self.current_search_tag = self.buffer.create_tag("current-search-result", background="#ff7800", foreground="#1f1f1f")
        scroller.set_child(self.text_view)
        reader_box.append(scroller)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status.add_css_class("status-bar")
        self.status_left = Gtk.Label(label="", xalign=0)
        self.status_left.set_hexpand(True)
        self.status_right = Gtk.Label(label="100%", xalign=1)
        status.append(self.status_left)
        status.append(self.status_right)
        reader_box.append(status)
        self.stack.add_named(reader_box, "reader")
        self.stack.set_visible_child_name("welcome")

    def _install_actions(self) -> None:
        actions = {
            "open": self._choose_file,
            "find": lambda *_: self.search_button.set_active(True),
            "zoom-in": lambda *_: self._set_zoom(self.zoom + 0.1),
            "zoom-out": lambda *_: self._set_zoom(self.zoom - 0.1),
            "zoom-reset": lambda *_: self._set_zoom(1.0),
            "details": self._show_details,
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _install_drop_target(self) -> None:
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self._drop_file)
        self.add_controller(drop)

    def _drop_file(self, _target: Gtk.DropTarget, value: object, _x: float, _y: float) -> bool:
        if isinstance(value, Gio.File):
            self.open_file(value)
            return True
        return False

    def _choose_file(self, *_args: object) -> None:
        dialog = Gtk.FileDialog(title="Open an RTF document", modal=True)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        rtf_filter = Gtk.FileFilter(name="Rich Text documents")
        rtf_filter.add_mime_type("application/rtf")
        rtf_filter.add_mime_type("text/rtf")
        rtf_filter.add_pattern("*.rtf")
        rtf_filter.add_pattern("*.RTF")
        filters.append(rtf_filter)
        dialog.set_filters(filters)
        dialog.open(self, None, self._file_chosen)

    def _file_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error as error:
            if not error.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                self._error("Could not open the file chooser", error.message)
            return
        self.open_file(file)

    def open_file(self, file: Gio.File) -> None:
        path = file.get_path()
        if not path:
            self._error("Remote files are not supported yet", "Save the file locally, then open it again.")
            return
        try:
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE:
                raise ValueError("The document is larger than the 40 MB safety limit.")
            document = parse_rtf(Path(path).read_bytes())
        except (OSError, ValueError) as error:
            self._error("Could not read this document", str(error))
            return

        self.current_file = file
        self.document = document
        self.zoom = 1.0
        self._render_document()
        display_name = file.get_basename() or "Untitled.rtf"
        self.title_label.set_label(document.title or display_name)
        self.set_title(f"{document.title or display_name} — Readleaf")
        words = len(document.text.split())
        self.status_left.set_label(f"{words:,} words  ·  {len(document.text):,} characters")
        self.status_right.set_label("100%")
        self.stack.set_visible_child_name("reader")
        self.search_button.set_sensitive(True)

    def _render_document(self) -> None:
        if not self.document:
            return
        self.buffer.set_text(self.document.text)
        self._tag_cache.clear()
        for span in self.document.spans:
            tag = self._tag_for_style(span.style)
            self.buffer.apply_tag(tag, self.buffer.get_iter_at_offset(span.start), self.buffer.get_iter_at_offset(span.end))
        self._search_changed(self.search_entry)

    def _tag_for_style(self, style: TextStyle) -> Gtk.TextTag:
        if style in self._tag_cache:
            return self._tag_cache[style]
        tag = Gtk.TextTag()
        tag.set_property("size-points", style.size * self.zoom)
        if style.bold:
            tag.set_property("weight", Pango.Weight.BOLD)
        if style.italic:
            tag.set_property("style", Pango.Style.ITALIC)
        if style.underline:
            tag.set_property("underline", Pango.Underline.SINGLE)
        if style.strike:
            tag.set_property("strikethrough", True)
        if style.font:
            tag.set_property("family", style.font)
        if style.foreground:
            tag.set_property("foreground", style.foreground)
        if style.background:
            tag.set_property("background", style.background)
        if style.alignment != "left":
            tag.set_property("justification", {
                "center": Gtk.Justification.CENTER,
                "right": Gtk.Justification.RIGHT,
                "fill": Gtk.Justification.FILL,
            }.get(style.alignment, Gtk.Justification.LEFT))
        if style.rise:
            tag.set_property("rise", int((5 if style.rise == "super" else -3) * Pango.SCALE * self.zoom))
            tag.set_property("scale", 0.8)
        self.buffer.get_tag_table().add(tag)
        self._tag_cache[style] = tag
        return tag

    def _set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.6, min(2.2, round(zoom, 1)))
        self.status_right.set_label(f"{round(self.zoom * 100):d}%")
        if self.document:
            self._render_document()

    def _toggle_search(self, button: Gtk.ToggleButton) -> None:
        active = button.get_active()
        self.search_bar.set_search_mode(active)
        if active:
            self.search_entry.grab_focus()

    def _search_changed(self, entry: Gtk.SearchEntry) -> None:
        start, end = self.buffer.get_bounds()
        self.buffer.remove_tag(self.search_tag, start, end)
        self.buffer.remove_tag(self.current_search_tag, start, end)
        self.matches.clear()
        self.match_index = -1
        query = entry.get_text()
        if not query:
            self.search_count.set_label("")
            return
        cursor = self.buffer.get_start_iter()
        flags = Gtk.TextSearchFlags.CASE_INSENSITIVE | Gtk.TextSearchFlags.TEXT_ONLY
        while True:
            result = cursor.forward_search(query, flags, None)
            if result is None:
                break
            match_start, match_end = result
            offsets = (match_start.get_offset(), match_end.get_offset())
            self.matches.append(offsets)
            self.buffer.apply_tag(self.search_tag, match_start, match_end)
            cursor = match_end
        if self.matches:
            self.match_index = 0
            self._show_current_match()
        else:
            self.search_count.set_label("No results")

    def _move_match(self, direction: int) -> None:
        if not self.matches:
            return
        self.match_index = (self.match_index + direction) % len(self.matches)
        self._show_current_match()

    def _show_current_match(self) -> None:
        start_all, end_all = self.buffer.get_bounds()
        self.buffer.remove_tag(self.current_search_tag, start_all, end_all)
        start_offset, end_offset = self.matches[self.match_index]
        start = self.buffer.get_iter_at_offset(start_offset)
        end = self.buffer.get_iter_at_offset(end_offset)
        self.buffer.apply_tag(self.current_search_tag, start, end)
        self.buffer.place_cursor(start)
        self.text_view.scroll_to_iter(start, 0.15, True, 0.5, 0.35)
        self.search_count.set_label(f"{self.match_index + 1} of {len(self.matches)}")

    def _show_details(self, *_args: object) -> None:
        if not self.document or not self.current_file:
            return
        rows = [f"File: {self.current_file.get_basename()}"]
        if self.document.title:
            rows.append(f"Title: {self.document.title}")
        if self.document.author:
            rows.append(f"Author: {self.document.author}")
        rows.append(f"Words: {len(self.document.text.split()):,}")
        dialog = Gtk.AlertDialog(message="Document details", detail="\n".join(rows))
        dialog.show(self)

    def _error(self, heading: str, detail: str) -> None:
        Gtk.AlertDialog(message=heading, detail=detail).show(self)


class ReadleafApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._about)
        self.add_action(about)
        for action, shortcuts in {
            "win.open": ["<Control>o"],
            "win.find": ["<Control>f"],
            "win.zoom-in": ["<Control>plus", "<Control>equal"],
            "win.zoom-out": ["<Control>minus"],
            "win.zoom-reset": ["<Control>0"],
            "app.quit": ["<Control>q"],
        }.items():
            self.set_accels_for_action(action, shortcuts)

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is None:
            window = ReaderWindow(self)
        window.present()

    def do_open(self, files: list[Gio.File], _n_files: int, _hint: str) -> None:
        self.do_activate()
        window = self.get_active_window()
        if files and isinstance(window, ReaderWindow):
            window.open_file(files[0])

    def _about(self, *_args: object) -> None:
        Gtk.AboutDialog(
            transient_for=self.get_active_window(),
            modal=True,
            program_name="Readleaf",
            version="1.0.0",
            comments="A calm, lightweight RTF reader for Linux.",
            website="https://github.com/",
            license_type=Gtk.License.MIT_X11,
            authors=["Readleaf contributors"],
            logo_icon_name=APP_ID,
        ).present()


def main() -> int:
    app = ReadleafApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
