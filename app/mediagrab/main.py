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
from mediagrab.formatting import format_eta
from mediagrab.media_inspector import ManifestInspection, inspect_manifest
from mediagrab.capture import MediaKind, HLSVariant
from mediagrab.task_factory import create_download_task
from mediagrab.queue_store import load_queue, save_queue
from mediagrab.settings_store import load_settings, save_settings
from mediagrab.url_utils import redact_url


APP_ID = "io.github.SakibShahariar.MediaGrab"
MAX_CONCURRENT_DOWNLOADS = 3


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
        super().__init__(title=title, subtitle=redact_url(url))
        self.window = window
        self.url = url
        self.task = task
        self.is_active = False
        self._source_url = redact_url(url)
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
        self.window.cancel_download(self)

    def update_progress(self, progress: DownloadProgress) -> None:
        if progress.total and progress.total > 0:
            self.progress.set_fraction(min(progress.received / progress.total, 1.0))
            size_text = f"{format_size(progress.received)} / {format_size(progress.total)}"
            remaining = progress.total - progress.received
            eta = format_eta(remaining / progress.bytes_per_second) if progress.bytes_per_second > 0 and remaining > 0 else None
            if eta:
                size_text = f"{size_text} · {eta}"
        else:
            self.progress.pulse()
            size_text = f"{format_size(progress.received)} received"

        if progress.state == "completed":
            self.status_label.set_text("Completed")
            self.cancel_button.set_visible(False)
        elif self.is_active:
            self.status_label.set_text(format_bytes(progress.bytes_per_second))
        self.set_subtitle(f"{self._source_url} · {size_text}")

    def finish(self, state: str, message: str | None = None) -> None:
        self.status_label.set_text(state)
        self.cancel_button.set_sensitive(False)
        self.cancel_button.set_visible(False)
        self.retry_button.set_visible(state in {"Failed", "Cancelled", "Interrupted"})
        if state == "Failed" and message:
            self.set_subtitle(f"{self._source_url} · {message}")
        elif state in {"Cancelled", "Interrupted"}:
            self.set_subtitle(f"{self._source_url} · Partial data may remain in Downloads")


class MediaGrabWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.set_title("MediaGrab")
        self.set_default_size(1000, 680)
        self._rows: list[DownloadRow] = []
        self._pending_downloads: list[DownloadRow] = []
        self._active_downloads: set[DownloadRow] = set()
        self.download_directory = Path(load_settings()["download_directory"])

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)
        header.set_title_widget(Adw.WindowTitle(title="MediaGrab", subtitle="Downloads"))

        destination_button = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        destination_button.set_tooltip_text("Choose download folder")
        destination_button.add_css_class("flat")
        destination_button.connect("clicked", self._on_choose_destination)
        header.pack_end(destination_button)

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

        self.destination_label = Gtk.Label(label=f"Files are saved to {self.download_directory}")
        self.destination_label.add_css_class("dim-label")
        self.destination_label.set_xalign(0)
        self.destination_label.set_ellipsize(Pango.EllipsizeMode.END)
        intro.append(self.destination_label)

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
            label=f"Up to {MAX_CONCURRENT_DOWNLOADS} simultaneous downloads · "
            "HLS/DASH streams use FFmpeg · automatic capture is in development"
        )
        footer.add_css_class("dim-label")
        footer.add_css_class("caption")
        footer.set_xalign(0)
        content.append(footer)
        self._restore_queue()

    def _on_choose_destination(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Choose download folder", self, Gtk.FileChooserAction.SELECT_FOLDER,
            "Select", "Cancel",
        )
        try:
            dialog.set_current_folder(Gio.File.new_for_path(str(self.download_directory)))
        except (GLib.Error, TypeError):
            pass
        dialog.connect("response", self._on_destination_response)
        dialog.show()

    def _on_destination_response(self, dialog: Gtk.FileChooserNative, response: int) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            selected = dialog.get_file()
            path = selected.get_path() if selected is not None else None
            if not path:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not read the selected folder."))
                return
            new_directory = Path(path)
            try:
                save_settings({"download_directory": str(new_directory)})
            except (OSError, ValueError) as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save download folder: {exc}"))
                return
            self.download_directory = new_directory
            self.destination_label.set_text(f"Files are saved to {self.download_directory}")
            self.toast_overlay.add_toast(Adw.Toast.new("Download folder updated."))
        finally:
            dialog.destroy()

    def _restore_queue(self) -> None:
        for entry in load_queue():
            url = entry["url"]
            try:
                task = create_download_task(url, self.download_directory)
            except ValueError:
                continue
            row = DownloadRow(self, url, task)
            row.finish("Interrupted")
            self._rows.append(row)
            self.list_box.append(row)
        self._update_count()
        self._persist_queue()

    def _update_count(self) -> None:
        count = len(self._rows)
        self.count_label.set_text(f"{count} item" + ("" if count == 1 else "s"))

    def _persist_queue(self) -> None:
        # Completed items are history only; unfinished items are restored as retryable.
        entries = [
            {"url": row.url}
            for row in self._rows
            if row.status_label.get_text() != "Completed"
        ]
        try:
            save_queue(entries)
        except OSError as exc:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not save queue state: {exc}")
            )

    def _make_empty_state(self) -> Gtk.Widget:
        page = Adw.StatusPage()
        page.set_icon_name("folder-download-symbolic")
        page.set_title("Nothing queued")
        page.set_description("Add a direct file URL or an HLS/DASH manifest URL to start a download.")
        return page

    def _on_add_clicked(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Add a download",
            body=f"Enter a direct file URL or an HLS/DASH manifest URL. The file will be saved in {self.download_directory}. HLS/DASH downloads require FFmpeg.",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("https://example.com/file.zip")
        entry.set_hexpand(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("inspect", "Inspect media…")
        dialog.add_response("add", "Download")
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_add_response, entry)
        dialog.present(self)

    def _on_add_response(
        self, _dialog: Adw.AlertDialog, response: str, entry: Gtk.Entry
    ) -> None:
        if response not in {"add", "inspect"}:
            return

        url = entry.get_text().strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid HTTP(S) URL."))
            return

        if response == "inspect":
            self.inspect_media_url(url)
            return
        self.add_download_url(url)

    def inspect_media_url(self, url: str) -> None:
        """Inspect a manifest off the GTK thread, then offer available HLS qualities."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid HTTP(S) URL."))
            return
        if parsed.username is not None or parsed.password is not None:
            self.toast_overlay.add_toast(Adw.Toast.new("URLs with embedded credentials are not accepted."))
            return
        self.toast_overlay.add_toast(Adw.Toast.new("Inspecting media manifest…"))

        def worker() -> None:
            try:
                result = inspect_manifest(url)
                GLib.idle_add(self._show_manifest_choices, url, result, None)
            except (ValueError, OSError) as exc:
                GLib.idle_add(self._show_manifest_choices, url, None, str(exc))

        threading.Thread(target=worker, daemon=True, name="mediagrab-inspect").start()

    def _show_manifest_choices(self, original_url: str, result: ManifestInspection | None, error: str | None) -> bool:
        if error or result is None:
            self.toast_overlay.add_toast(Adw.Toast.new("Could not inspect manifest: " + (error or "unknown error")))
            return GLib.SOURCE_REMOVE

        choices: list[tuple[str, str]] = [("Use original manifest (FFmpeg chooses streams)", original_url)]
        if result.kind is MediaKind.HLS:
            variants = sorted(result.variants, key=lambda item: (item.height or 0, item.bandwidth or 0))
            for variant in variants:
                choices.append((self._variant_label(variant), variant.url))

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(content, "set_margin_" + side)(6)
        if len(choices) > 1:
            dropdown = Gtk.DropDown(model=Gtk.StringList.new([label for label, _url in choices]))
            dropdown.set_selected(0)
            content.append(Gtk.Label(label="Download choice", xalign=0))
            content.append(dropdown)
        else:
            dropdown = None
            content.append(Gtk.Label(label="No separate quality variants were declared. The original manifest will be queued.", wrap=True))

        details = ["Type: " + result.kind.value.upper()]
        if result.kind is MediaKind.HLS:
            audio_count = sum(item.kind == "audio" for item in result.renditions)
            subtitle_count = sum(item.kind == "subtitles" for item in result.renditions)
            details.append("Declared alternate tracks: " + str(audio_count) + " audio, " + str(subtitle_count) + " subtitle")
        elif result.representations:
            details.append("DASH representations declared: " + str(len(result.representations)))
        content.append(Gtk.Label(label="\n".join(details), xalign=0, wrap=True))
        content.append(Gtk.Label(label="Manifest metadata is not a guarantee of availability. Alternate HLS audio/subtitle tracks may require the original manifest.", xalign=0, wrap=True))

        dialog = Adw.AlertDialog(heading="Media choices", body="Choose a stream to add to the download queue.")
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("download", "Add to queue")
        dialog.set_default_response("download")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)

        def response_cb(_dialog: Adw.AlertDialog, response: str) -> None:
            if response == "download":
                index = dropdown.get_selected() if dropdown is not None else 0
                index = min(index, len(choices) - 1)
                self.add_download_url(choices[index][1])

        dialog.connect("response", response_cb)
        dialog.present(self)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _variant_label(variant: HLSVariant) -> str:
        resolution = str(variant.width) + "×" + str(variant.height) if variant.width and variant.height else "Unknown resolution"
        bitrate = " · " + str(round(variant.bandwidth / 1000)) + " kb/s" if variant.bandwidth else ""
        codecs = " · " + variant.codecs if variant.codecs else ""
        return resolution + bitrate + codecs

    def add_download_url(self, url: str) -> bool:
        """Validate and enqueue a URL from either the UI or browser bridge."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid HTTP(S) URL."))
            return False
        if parsed.username is not None or parsed.password is not None:
            self.toast_overlay.add_toast(Adw.Toast.new("URLs with embedded credentials are not accepted."))
            return False
        try:
            task = create_download_task(url, self.download_directory)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return False
        row = DownloadRow(self, url, task)
        self._rows.append(row)
        self.list_box.append(row)
        self._update_count()
        self._persist_queue()
        self._enqueue_download(row)
        self.toast_overlay.add_toast(Adw.Toast.new("Added to download queue."))
        return True

    def _enqueue_download(self, row: DownloadRow) -> None:
        if row in self._pending_downloads or row in self._active_downloads:
            return
        self._pending_downloads.append(row)
        row.status_label.set_text("Queued")
        self._start_next_downloads()

    def _start_next_downloads(self) -> None:
        while (
            self._pending_downloads
            and len(self._active_downloads) < MAX_CONCURRENT_DOWNLOADS
        ):
            row = self._pending_downloads.pop(0)
            self._active_downloads.add(row)
            row.is_active = True
            row.status_label.set_text("Starting…")
            threading.Thread(
                target=self._run_download,
                args=(row.task, row),
                daemon=True,
                name="mediagrab-download",
            ).start()

    def cancel_download(self, row: DownloadRow) -> None:
        if row in self._pending_downloads:
            self._pending_downloads.remove(row)
            row.finish("Cancelled")
            self._persist_queue()
            self.toast_overlay.add_toast(Adw.Toast.new("Queued download cancelled."))
            return
        if row in self._active_downloads:
            row.task.cancel()
            row.status_label.set_text("Cancelling…")
            row.cancel_button.set_sensitive(False)

    def retry_download(self, row: DownloadRow) -> None:
        if row in self._pending_downloads or row in self._active_downloads:
            return
        try:
            task = create_download_task(row.url, self.download_directory)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return
        row.prepare_retry(task)
        self._persist_queue()
        self._enqueue_download(row)
        self.toast_overlay.add_toast(Adw.Toast.new("Retry added to queue."))

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
        row.is_active = False
        self._active_downloads.discard(row)
        row.finish(state, detail if state == "Failed" else None)
        if state == "Completed":
            self.toast_overlay.add_toast(Adw.Toast.new(f"Saved: {detail}"))
        elif state == "Failed":
            self.toast_overlay.add_toast(Adw.Toast.new(f"Download failed: {detail}"))
        elif state == "Cancelled":
            self.toast_overlay.add_toast(Adw.Toast.new("Download cancelled."))
        self._persist_queue()
        self._start_next_downloads()
        return GLib.SOURCE_REMOVE


class MediaGrabApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.connect("activate", self._on_activate)
        self.connect("command-line", self._on_command_line)

    def _on_activate(self, app: Adw.Application) -> None:
        window = app.get_active_window()
        if window is None:
            window = MediaGrabWindow(application=app)
        window.present()

    def _on_command_line(self, app: Adw.Application, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        url: str | None = None
        if args:
            if len(args) != 2 or args[0] != "--add-url":
                command_line.print("Usage: mediagrab [--add-url HTTP(S)_URL]\\n")
                return 2
            url = args[1]
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                command_line.print("MediaGrab accepts only valid HTTP(S) URLs.\\n")
                return 2
            if parsed.username is not None or parsed.password is not None:
                command_line.print("URLs containing embedded credentials are not accepted.\\n")
                return 2
        self._on_activate(app)
        window = app.get_active_window()
        if url is not None and isinstance(window, MediaGrabWindow):
            if not window.add_download_url(url):
                return 2
        return 0


def main() -> int:
    app = MediaGrabApplication()
    return app.run(sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
