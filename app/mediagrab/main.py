"""Initial GTK4/libadwaita application shell for MediaGrab."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


APP_ID = "io.github.SakibShahariar.MediaGrab"


class DownloadRow(Adw.ActionRow):
    """Simple presentation row for a queued download candidate."""

    def __init__(self, url: str) -> None:
        parsed = urlparse(url)
        title = parsed.path.rsplit("/", 1)[-1] or parsed.netloc or url
        super().__init__(title=title, subtitle=url)
        self.set_activatable(False)
        self.add_prefix(Gtk.Image.new_from_icon_name("folder-download-symbolic"))
        self.add_suffix(Gtk.Label(label="Queued"))
        self.set_subtitle(url)


class MediaGrabWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.set_title("MediaGrab")
        self.set_default_size(1000, 680)
        self._rows: list[DownloadRow] = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        title = Adw.WindowTitle(title="MediaGrab", subtitle="Downloads")
        header.set_title_widget(title)

        add_button = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_button.set_tooltip_text("Add a download URL")
        add_button.add_css_class("suggested-action")
        add_button.connect("clicked", self._on_add_clicked)
        header.pack_end(add_button)

        self.toast_overlay = Adw.ToastOverlay()
        root.append(self.toast_overlay)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(28)
        content.set_margin_end(28)
        self.toast_overlay.set_child(content)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content.append(heading)

        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        intro.set_hexpand(True)
        heading.append(intro)

        page_title = Gtk.Label(label="Your downloads")
        page_title.add_css_class("title-1")
        page_title.set_xalign(0)
        intro.append(page_title)

        description = Gtk.Label(
            label="Manage download tasks in one native desktop app."
        )
        description.add_css_class("dim-label")
        description.set_xalign(0)
        intro.append(description)

        self.count_label = Gtk.Label(label="0 items")
        self.count_label.add_css_class("dim-label")
        heading.append(self.count_label)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_placeholder(self._make_empty_state())

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.list_box)
        content.append(scroller)

        footer = Gtk.Label(
            label="Early development build · Downloads are not implemented yet"
        )
        footer.add_css_class("dim-label")
        footer.add_css_class("caption")
        footer.set_xalign(0)
        content.append(footer)

    def _make_empty_state(self) -> Gtk.Widget:
        page = Adw.StatusPage()
        page.set_icon_name("folder-download-symbolic")
        page.set_title("Nothing queued")
        page.set_description(
            "Add a direct download URL to preview the queue workflow. "
            "Transfers will be implemented in a later milestone."
        )
        return page

    def _on_add_clicked(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Add a download",
            body="Enter an HTTP or HTTPS URL. This prototype only adds it to the queue.",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("https://example.com/file.zip")
        entry.set_hexpand(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add to queue")
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_add_response, entry)
        dialog.present(self)

    def _on_add_response(
        self, _dialog: Adw.AlertDialog, response: str, entry: Gtk.Entry
    ) -> None:
        if response != "add":
            return

        url = entry.get_text().strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid HTTP(S) URL."))
            return

        row = DownloadRow(url)
        self._rows.append(row)
        self.list_box.append(row)
        self.count_label.set_text(
            f"{len(self._rows)} item" + ("" if len(self._rows) == 1 else "s")
        )
        self.toast_overlay.add_toast(Adw.Toast.new("Added to the prototype queue."))


class MediaGrabApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)

    def _on_activate(self, app: Adw.Application) -> None:
        window = app.get_active_window()
        if window is None:
            window = MediaGrabWindow(application=app)
        window.present()


def main() -> int:
    app = MediaGrabApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
