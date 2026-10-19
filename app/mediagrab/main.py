"""GTK4/libadwaita UI for MediaGrab's basic download workflow."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from mediagrab.downloader import DownloadError, DownloadProgress, DownloadTask


APP_ID = "io.github.SakibShahariar.MediaGrab"
DOWNLOAD_DIRECTORY = Path.home() / "Downloads"


def format_bytes(value: float) -> str:
    units = ("B/s", "KB/s", "MB/s", "GB/s")
    amount = value
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GB/s"


def format_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


class DownloadRow(Adw.ActionRow):
    """One queue item, including progress, cancellation, and retry controls."""

    def __init__(self, window: "MediaGrabWindow", url: str, task: DownloadTask) -> None:
        parsed = urlparse(url)
        title = parsed.path.rsplit("/", 1)[-1] or parsed.netloc or url
        super().__init__(title=title, subtitle=url)
        self.window = window
        self.url = url
        self.task = task
        self.set_activatable(False)
        self.add_prefix(Gtk.Image.new_from_icon_name("folder-download-symbolic"))

        self.status_label = Gtk.Label(label="Queued")
        self.status_label.set_width_chars(14)
        self.status_label.set_xalign(1)
        self.add_suffix(self.status_label)

        self.progress = Gtk.ProgressBar()
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_size_request(120, -1)
        self.add_suffix(self.progress)

        self.retry_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.retry_button.set_tooltip_text("Retry or resume download")
        self.retry_button.add_css_class("flat")
        self.retry_button.set_visible(False)
        self.retry_button.connect("clicked", self._on_retry)
        self.add_suffix(self.retry_button)

        self.cancel_button = Gtk.Button.new_from_icon_name("process-stop-symbolic")
        self.cancel_button.set_tooltip_text("Cancel download")
        self.cancel_button.add_css_class("flat")
        self.cancel_button.connect("clicked", self._on_cancel)
        self.add_suffix(self.cancel_button)

    def _on_retry(self, _button: Gtk.Button) -> None:
        self.window.retry_download(self)

    def prepare_retry(self, task: DownloadTask) -> None:
        self.task = task
        self.status_label.set_text("Queued")
        self.progress.set_fraction(0)
        self.progress.set_text(None)
        self.cancel_button.set_sensitive(True)
        self.cancel_button.set_visible(True)
        self.retry_button.set_visible(False)
        self.set_subtitle(self._source_url)

    def _on_cancel(self, _button: Gtk.Button) -> None:
        self.task.cancel()
        self.status_label.set_text("Cancelling…")
        self.cancel_button.set_sensitive(False)

    def update_progress(self, progress: DownloadProgress) -> None:
        if progress.total and progress.total > 0:
            self.progress.set_fraction(min(progress.received / progress.total, 1.0))
            size_text = f"{format_size(progress.received)} / {format_size(progress.total)}"
        else:
            self.progress.pulse()
            size_text = f"{format_size(progress.received)} received"

        if progress.state == "completed":
            self.status_label.set_text("Completed")
            self.cancel_button.set_visible(False)
        else:
            self.status_label.set_text(format_bytes(progress.bytes_per_second))
        self.set_subtitle(f"{self.get_subtitle_url()} · {size_text}")

    def get_subtitle_url(self) -> str:
        # Keep the source URL as the stable first part of the subtitle.
        return self._source_url

    def set_source_url(self, url: str) -> None:
        self._source_url = url

    def finish(self, state: str, message: str | None = None) -> None:
        self.status_label.set_text(state)
        self.cancel_button.set_sensitive(False)
        self.cancel_button.set_visible(False)
        self.retry_button.set_visible(state in {"Failed", "Cancelled"})
        if state == "Failed" and message:
            self.set_subtitle(f"{self._source_url} · {message}")
        elif state == "Cancelled":
            self.set_subtitle(f"{self._source_url} · Partial data may remain in Downloads")


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
        header.set_title_widget(Adw.WindowTitle(title="MediaGrab", subtitle="Downloads"))

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

        description = Gtk.Label(label=f"Files are saved to {DOWNLOAD_DIRECTORY}")
        description.add_css_class("dim-label")
        description.set_xalign(0)
        description.set_ellipsize(Pango.EllipsizeMode.END)
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

        footer = Gtk.Label(label="Basic HTTP/HTTPS downloads · Browser capture not yet implemented")
        footer.add_css_class("dim-label")
        footer.add_css_class("caption")
        footer.set_xalign(0)
        content.append(footer)

    def _make_empty_state(self) -> Gtk.Widget:
        page = Adw.StatusPage()
        page.set_icon_name("folder-download-symbolic")
        page.set_title("Nothing queued")
        page.set_description("Add a direct HTTP(S) file URL to start a download.")
        return page

    def _on_add_clicked(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Add a download",
            body=f"Enter a direct HTTP(S) URL. The file will be saved in {DOWNLOAD_DIRECTORY}.",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("https://example.com/file.zip")
        entry.set_hexpand(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Download")
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

        try:
            task = DownloadTask(url, DOWNLOAD_DIRECTORY)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return

        row = DownloadRow(self, url, task)
        row.set_source_url(url)
        self._rows.append(row)
        self.list_box.append(row)
        self.count_label.set_text(
            f"{len(self._rows)} item" + ("" if len(self._rows) == 1 else "s")
        )
        self.toast_overlay.add_toast(Adw.Toast.new("Download started."))

        self._start_download(task, row)

    def _start_download(self, task: DownloadTask, row: DownloadRow) -> None:
        threading.Thread(
            target=self._run_download,
            args=(task, row),
            daemon=True,
            name="mediagrab-download",
        ).start()

    def retry_download(self, row: DownloadRow) -> None:
        try:
            task = DownloadTask(row.url, DOWNLOAD_DIRECTORY)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return
        row.prepare_retry(task)
        self.toast_overlay.add_toast(Adw.Toast.new("Retrying download…"))
        self._start_download(task, row)

    def _run_download(self, task: DownloadTask, row: DownloadRow) -> None:
        try:
            target = task.run(
                lambda progress: GLib.idle_add(row.update_progress, progress)
            )
            GLib.idle_add(self._download_finished, row, "Completed", str(target))
        except DownloadError as exc:
            state = "Cancelled" if task.state == "cancelled" else "Failed"
            GLib.idle_add(self._download_finished, row, state, str(exc))
        except Exception as exc:  # Keep an unexpected worker error from silently losing the queue row.
            GLib.idle_add(
                self._download_finished,
                row,
                "Failed",
                f"Unexpected error ({type(exc).__name__}): {exc}",
            )

    def _download_finished(self, row: DownloadRow, state: str, detail: str) -> bool:
        row.finish(state, detail if state == "Failed" else None)
        if state == "Completed":
            self.toast_overlay.add_toast(Adw.Toast.new(f"Saved: {detail}"))
        elif state == "Failed":
            self.toast_overlay.add_toast(Adw.Toast.new(f"Download failed: {detail}"))
        elif state == "Cancelled":
            self.toast_overlay.add_toast(Adw.Toast.new("Download cancelled."))
        return GLib.SOURCE_REMOVE


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
