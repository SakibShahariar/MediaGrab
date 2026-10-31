"""GTK4/libadwaita UI for MediaGrab's basic download workflow."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from mediagrab.downloader import DownloadError, DownloadPaused, DownloadProgress, DownloadTask
from mediagrab.formatting import format_eta
from mediagrab.media_inspector import ManifestInspection, inspect_manifest
from mediagrab.capture import MediaKind, HLSVariant
from mediagrab.task_factory import create_download_task
from mediagrab.queue_store import load_queue, save_queue
from mediagrab.settings_store import load_settings, save_settings
from mediagrab.diagnostics import configure_logging, get_logger, log_event, read_diagnostics
from mediagrab.url_utils import is_valid_http_url, redact_url
from mediagrab.cli import parse_command


APP_ID = "io.github.SakibShahariar.MediaGrab"
MAX_CONCURRENT_DOWNLOADS = 3
_LOG = get_logger("application")
_DIAGNOSTIC_LEVELS = ("ERROR", "WARNING", "INFO", "DEBUG")


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

    def __init__(self, window: "MediaGrabWindow", url: str, task: DownloadTask, *, audio_url: str | None = None, subtitle_url: str | None = None) -> None:
        parsed = urlparse(url)
        title = parsed.path.rsplit("/", 1)[-1] or parsed.netloc or url
        super().__init__(title=title, subtitle=redact_url(url))
        self.window = window
        self.url = url
        self.audio_url = audio_url
        self.subtitle_url = subtitle_url
        self.task = task
        self.is_active = False
        self._source_url = redact_url(url)
        self._search_text = f"{title} {url}".casefold()
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

        self.candidate_action_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.candidate_action_button.set_tooltip_text("Download detected media")
        self.candidate_action_button.add_css_class("flat")
        self.candidate_action_button.set_visible(False)
        self.candidate_action_button.connect("clicked", self._on_candidate_action)
        self.add_suffix(self.candidate_action_button)

        self.dismiss_candidate_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        self.dismiss_candidate_button.set_tooltip_text("Dismiss detected media")
        self.dismiss_candidate_button.add_css_class("flat")
        self.dismiss_candidate_button.set_visible(False)
        self.dismiss_candidate_button.connect("clicked", self._on_dismiss_candidate)
        self.add_suffix(self.dismiss_candidate_button)

        self.pause_button = Gtk.Button.new_from_icon_name("media-playback-pause-symbolic")
        self.pause_button.set_tooltip_text("Pause direct download")
        self.pause_button.add_css_class("flat")
        self.pause_button.set_visible(isinstance(task, DownloadTask))
        self.pause_button.connect("clicked", self._on_pause)
        self.add_suffix(self.pause_button)

        self.cancel_button = Gtk.Button.new_from_icon_name("process-stop-symbolic")
        self.cancel_button.set_tooltip_text("Cancel download")
        self.cancel_button.add_css_class("flat")
        self.cancel_button.connect("clicked", self._on_cancel)
        self.add_suffix(self.cancel_button)

    def _on_retry(self, _button: Gtk.Button) -> None:
        self.window.retry_download(self)

    def _on_candidate_action(self, _button: Gtk.Button) -> None:
        if isinstance(self.task, DownloadTask):
            self.window.retry_download(self)
        else:
            self.window.inspect_media_url(self.url)

    def _on_dismiss_candidate(self, _button: Gtk.Button) -> None:
        self.window.dismiss_candidate(self)

    def prepare_retry(self, task: DownloadTask) -> None:
        self.task = task
        self.status_label.set_text("Queued")
        self.progress.set_fraction(0)
        self.progress.set_text(None)
        self.cancel_button.set_sensitive(True)
        self.cancel_button.set_visible(True)
        self.pause_button.set_visible(isinstance(task, DownloadTask))
        self.pause_button.set_sensitive(True)
        self.retry_button.set_visible(False)
        self.candidate_action_button.set_visible(False)
        self.dismiss_candidate_button.set_visible(False)
        self.progress.set_visible(True)
        self.set_subtitle(self._source_url)

    def _on_cancel(self, _button: Gtk.Button) -> None:
        self.window.cancel_download(self)

    def _on_pause(self, _button: Gtk.Button) -> None:
        self.window.pause_download(self)

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
            self.pause_button.set_visible(False)
        elif self.is_active:
            self.status_label.set_text(format_bytes(progress.bytes_per_second))
        self.set_subtitle(f"{self._source_url} · {size_text}")

    def finish(self, state: str, message: str | None = None) -> None:
        self.status_label.set_text(state)
        self.cancel_button.set_sensitive(False)
        self.cancel_button.set_visible(False)
        self.pause_button.set_sensitive(False)
        self.pause_button.set_visible(False)
        is_candidate = state == "Detected"
        self.retry_button.set_visible(state in {"Failed", "Cancelled", "Interrupted", "Paused"})
        self.candidate_action_button.set_visible(is_candidate)
        self.dismiss_candidate_button.set_visible(is_candidate)
        self.progress.set_visible(not is_candidate)
        if is_candidate:
            self.candidate_action_button.set_tooltip_text(
                "Inspect stream choices" if not isinstance(self.task, DownloadTask) else "Download detected media"
            )
        if state == "Failed" and message:
            self.set_subtitle(f"{self._source_url} · {message}")
        elif state in {"Cancelled", "Interrupted", "Paused"}:
            self.set_subtitle(f"{self._source_url} · Partial data may remain in Downloads")


class MediaGrabWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.set_title("MediaGrab")
        self.set_default_size(1000, 680)
        self._rows: list[DownloadRow] = []
        self._pending_downloads: list[DownloadRow] = []
        self._active_downloads: set[DownloadRow] = set()
        settings = load_settings()
        self.download_directory = Path(settings["download_directory"])
        self.max_concurrent_downloads = int(settings["max_concurrent_downloads"])

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)
        header.set_title_widget(Adw.WindowTitle(title="MediaGrab", subtitle="Downloads"))

        diagnostics_button = Gtk.Button.new_from_icon_name("dialog-information-symbolic")
        diagnostics_button.set_tooltip_text("Settings and diagnostics")
        diagnostics_button.add_css_class("flat")
        diagnostics_button.connect("clicked", self._on_diagnostics_clicked)
        header.pack_end(diagnostics_button)

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

        self.clear_completed_button = Gtk.Button(label="Clear completed")
        self.clear_completed_button.add_css_class("flat")
        self.clear_completed_button.set_tooltip_text("Remove completed downloads from this list")
        self.clear_completed_button.set_sensitive(False)
        self.clear_completed_button.connect("clicked", self._on_clear_completed)
        heading.append(self.clear_completed_button)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search downloads")
        self.search_entry.set_tooltip_text("Search by filename or source URL")
        self.search_entry.connect("search-changed", self._on_search_changed)
        content.append(self.search_entry)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_placeholder(self._make_empty_state())

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.list_box)
        content.append(scroller)

        self.footer_label = Gtk.Label(
            label=self._footer_text()
        )
        self.footer_label.add_css_class("dim-label")
        self.footer_label.add_css_class("caption")
        self.footer_label.set_xalign(0)
        content.append(self.footer_label)
        self._restore_queue()

    def _footer_text(self) -> str:
        return (
            f"Up to {self.max_concurrent_downloads} simultaneous downloads · "
            "HLS/DASH streams use FFmpeg · browser detections wait for your review"
        )

    def _on_diagnostics_clicked(self, _button: Gtk.Button) -> None:
        settings = load_settings()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(6)
        content.set_margin_bottom(6)
        content.set_margin_start(6)
        content.set_margin_end(6)
        content.append(Gtk.Label(label="Logging verbosity", xalign=0))
        level = Gtk.DropDown(model=Gtk.StringList.new(list(_DIAGNOSTIC_LEVELS)))
        level.set_selected(_DIAGNOSTIC_LEVELS.index(settings["diagnostics_level"]))
        content.append(level)
        concurrency_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        concurrency_label = Gtk.Label(label="Maximum simultaneous downloads", xalign=0)
        concurrency_label.set_hexpand(True)
        concurrency = Gtk.SpinButton.new_with_range(1, 10, 1)
        concurrency.set_value(int(settings["max_concurrent_downloads"]))
        concurrency_row.append(concurrency_label)
        concurrency_row.append(concurrency)
        content.append(concurrency_row)
        copy_button = Gtk.Button(label="Copy redacted diagnostics")
        copy_button.add_css_class("flat")
        copy_button.connect("clicked", self._on_copy_diagnostics)
        content.append(copy_button)

        dialog = Adw.AlertDialog(
            heading="Settings and diagnostics",
            body="Choose how many downloads may run at once and how much diagnostic detail MediaGrab records. URLs, credentials, tokens, and personal paths are redacted before export.",
        )
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "save":
                return
            selected = level.get_selected()
            if selected >= len(_DIAGNOSTIC_LEVELS):
                return
            diagnostics_level = _DIAGNOSTIC_LEVELS[selected]
            try:
                save_settings({
                    "download_directory": str(self.download_directory),
                    "diagnostics_level": diagnostics_level,
                    "max_concurrent_downloads": concurrency.get_value_as_int(),
                })
                configure_logging(diagnostics_level)
                self.max_concurrent_downloads = concurrency.get_value_as_int()
                self.footer_label.set_text(self._footer_text())
                self._start_next_downloads()
            except (OSError, ValueError) as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save diagnostics settings: {exc}"))
                return
            self.toast_overlay.add_toast(Adw.Toast.new(f"Diagnostics verbosity set to {diagnostics_level}."))
        dialog.connect("response", on_response)
        dialog.present(self)

    def _on_copy_diagnostics(self, _button: Gtk.Button) -> None:
        try:
            contents = read_diagnostics()
            if not contents.strip():
                self.toast_overlay.add_toast(Adw.Toast.new("No diagnostics have been recorded yet."))
                return
            self.get_display().get_clipboard().set(contents)
        except OSError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Could not read diagnostics: {exc}"))
            return
        self.toast_overlay.add_toast(Adw.Toast.new("Redacted diagnostics copied to the clipboard."))

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
                settings = load_settings()
                save_settings({
                    "download_directory": str(new_directory),
                    "diagnostics_level": settings["diagnostics_level"],
                    "max_concurrent_downloads": settings["max_concurrent_downloads"],
                })
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
                task = create_download_task(url, self.download_directory, audio_url=entry.get("audio_url"), subtitle_url=entry.get("subtitle_url"))
            except ValueError:
                continue
            row = DownloadRow(self, url, task, audio_url=entry.get("audio_url"), subtitle_url=entry.get("subtitle_url"))
            row.finish("Detected" if entry.get("candidate") is True else "Interrupted")
            self._rows.append(row)
            self.list_box.append(row)
        self._update_count()
        self._persist_queue()

    def _update_count(self) -> None:
        count = len(self._rows)
        completed = sum(row.status_label.get_text() == "Completed" for row in self._rows)
        self.count_label.set_text(f"{count} item" + ("" if count == 1 else "s"))
        self.clear_completed_button.set_sensitive(completed > 0)

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        query = self.search_entry.get_text().strip().casefold()
        for row in self._rows:
            status = row.status_label.get_text().casefold()
            row.set_visible(not query or query in row._search_text or query in status)

    def _on_clear_completed(self, _button: Gtk.Button) -> None:
        completed = [row for row in self._rows if row.status_label.get_text() == "Completed"]
        if not completed:
            return
        for row in completed:
            self.list_box.remove(row)
            self._rows.remove(row)
        self._update_count()
        self._persist_queue()
        self.toast_overlay.add_toast(Adw.Toast.new(
            f"Removed {len(completed)} completed download" + ("" if len(completed) == 1 else "s") + " from the list."
        ))

    def _persist_queue(self) -> None:
        # Completed items are history only; unfinished items are restored as retryable.
        entries: list[dict[str, str | bool]] = []
        for row in self._rows:
            state = row.status_label.get_text()
            if state == "Completed":
                continue
            entry: dict[str, str | bool] = {
                "url": row.url,
                **({"audio_url": row.audio_url} if row.audio_url else {}),
                **({"subtitle_url": row.subtitle_url} if row.subtitle_url else {}),
            }
            if state == "Detected":
                entry["candidate"] = True
            entries.append(entry)
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
        paste_button = Gtk.Button(label="Paste")
        paste_button.set_tooltip_text("Read a URL from the clipboard")
        paste_button.add_css_class("flat")
        paste_button.connect("clicked", self._on_paste_clipboard, entry)
        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        entry_row.append(entry)
        entry_row.append(paste_button)
        dialog.set_extra_child(entry_row)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("inspect", "Inspect media…")
        dialog.add_response("add", "Download")
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_add_response, entry)
        dialog.present(self)

    def _on_paste_clipboard(self, _button: Gtk.Button, entry: Gtk.Entry) -> None:
        """Read clipboard text only after the user explicitly presses Paste."""
        clipboard = self.get_display().get_clipboard()
        clipboard.read_text_async(None, self._on_clipboard_text_read, entry)

    def _on_clipboard_text_read(
        self, clipboard: object, result: object, entry: Gtk.Entry
    ) -> None:
        try:
            value = clipboard.read_text_finish(result)  # type: ignore[attr-defined]
        except GLib.Error:
            self.toast_overlay.add_toast(Adw.Toast.new("Could not read text from the clipboard."))
            return
        url = value.strip() if isinstance(value, str) else ""
        if not url:
            self.toast_overlay.add_toast(Adw.Toast.new("The clipboard does not contain text."))
            return
        if not is_valid_http_url(url):
            self.toast_overlay.add_toast(Adw.Toast.new("The clipboard does not contain a valid credential-free HTTP(S) URL."))
            return
        entry.set_text(url)
        self.toast_overlay.add_toast(Adw.Toast.new("URL pasted. Review it before adding the download."))

    def _on_add_response(
        self, _dialog: Adw.AlertDialog, response: str, entry: Gtk.Entry
    ) -> None:
        if response not in {"add", "inspect"}:
            return

        url = entry.get_text().strip()
        if not is_valid_http_url(url):
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid credential-free HTTP(S) URL."))
            return

        if response == "inspect":
            self.inspect_media_url(url)
            return
        self.add_download_url(url)

    def inspect_media_url(self, url: str) -> None:
        """Inspect a manifest off the GTK thread, then offer available HLS qualities."""
        if not is_valid_http_url(url):
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid credential-free HTTP(S) URL."))
            return
        if parsed.username is not None or parsed.password is not None:
            self.toast_overlay.add_toast(Adw.Toast.new("URLs with embedded credentials are not accepted."))
            return
        log_event(_LOG, "manifest_inspection_started", url=url)
        self.toast_overlay.add_toast(Adw.Toast.new("Inspecting media manifest…"))

        def worker() -> None:
            try:
                result = inspect_manifest(url)
                GLib.idle_add(self._show_manifest_choices, url, result, None)
            except (ValueError, OSError) as exc:
                log_event(_LOG, "manifest_inspection_failed", level=40, url=url, error=str(exc))
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
                chosen_video = choices[index][1]
                selected_variant = next((item for item in result.variants if item.url == chosen_video), None)
                audio_url = None
                subtitle_url = None
                if audio_dropdown is not None:
                    audio_index = audio_dropdown.get_selected()
                    if audio_index > 0:
                        selected_audio = audio_choices[audio_index - 1]
                        if selected_variant is not None and selected_variant.audio_group and selected_audio.group_id != selected_variant.audio_group:
                            self.toast_overlay.add_toast(Adw.Toast.new("That audio track does not belong to the selected video variant."))
                            return
                        audio_url = selected_audio.url
                if subtitle_dropdown is not None:
                    subtitle_index = subtitle_dropdown.get_selected()
                    if subtitle_index > 0:
                        selected_subtitle = subtitle_choices[subtitle_index - 1]
                        if selected_variant is not None and selected_variant.subtitle_group and selected_subtitle.group_id != selected_variant.subtitle_group:
                            self.toast_overlay.add_toast(Adw.Toast.new("Those subtitles do not belong to the selected video variant."))
                            return
                        subtitle_url = selected_subtitle.url
                if self.add_download_url(chosen_video, audio_url=audio_url, subtitle_url=subtitle_url):
                    self.dismiss_candidate_by_url(original_url)

        audio_choices = [item for item in result.renditions if item.kind == "audio" and item.url]
        subtitle_choices = [item for item in result.renditions if item.kind == "subtitles" and item.url]
        audio_dropdown = None
        subtitle_dropdown = None
        if audio_choices:
            content.append(Gtk.Label(label="Alternate audio (optional)", xalign=0))
            audio_labels = ["Use variant/default audio"] + [(item.name or item.language or "Audio track") + ((" · " + item.language) if item.language else "") + ((" · group " + item.group_id) if item.group_id else "") for item in audio_choices]
            audio_dropdown = Gtk.DropDown(model=Gtk.StringList.new(audio_labels))
            content.append(audio_dropdown)
        if subtitle_choices:
            content.append(Gtk.Label(label="Subtitles (optional)", xalign=0))
            subtitle_labels = ["No extra subtitles"] + [(item.name or item.language or "Subtitle track") + ((" · " + item.language) if item.language else "") + ((" · group " + item.group_id) if item.group_id else "") for item in subtitle_choices]
            subtitle_dropdown = Gtk.DropDown(model=Gtk.StringList.new(subtitle_labels))
            content.append(subtitle_dropdown)
        dialog.connect("response", response_cb)
        dialog.present(self)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _variant_label(variant: HLSVariant) -> str:
        resolution = str(variant.width) + "×" + str(variant.height) if variant.width and variant.height else "Unknown resolution"
        bitrate = " · " + str(round(variant.bandwidth / 1000)) + " kb/s" if variant.bandwidth else ""
        codecs = " · " + variant.codecs if variant.codecs else ""
        return resolution + bitrate + codecs

    def add_candidate_url(self, url: str) -> bool:
        """Add a browser-detected URL to the review inbox without starting it."""
        if not is_valid_http_url(url):
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid credential-free HTTP(S) URL."))
            return False
        if any(row.url == url and row.status_label.get_text() == "Detected" for row in self._rows):
            self.toast_overlay.add_toast(Adw.Toast.new("This media candidate is already waiting for review."))
            return True
        try:
            task = create_download_task(url, self.download_directory)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return False
        row = DownloadRow(self, url, task)
        row.finish("Detected")
        self._rows.append(row)
        self.list_box.append(row)
        self._update_count()
        self._persist_queue()
        log_event(_LOG, "capture_candidate_added", url=url)
        self.toast_overlay.add_toast(Adw.Toast.new("Media candidate added for review."))
        return True

    def dismiss_candidate(self, row: DownloadRow) -> None:
        if row not in self._rows or row.status_label.get_text() != "Detected":
            return
        self.list_box.remove(row)
        self._rows.remove(row)
        self._update_count()
        self._persist_queue()
        log_event(_LOG, "capture_candidate_dismissed", url=row.url)
        self.toast_overlay.add_toast(Adw.Toast.new("Media candidate dismissed."))

    def dismiss_candidate_by_url(self, url: str) -> None:
        row = next(
            (item for item in self._rows if item.url == url and item.status_label.get_text() == "Detected"),
            None,
        )
        if row is not None:
            self.dismiss_candidate(row)

    def add_download_url(self, url: str, *, audio_url: str | None = None, subtitle_url: str | None = None) -> bool:
        """Validate and enqueue a URL from either the UI or browser bridge."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid HTTP(S) URL."))
            return False
        if parsed.username is not None or parsed.password is not None:
            self.toast_overlay.add_toast(Adw.Toast.new("URLs with embedded credentials are not accepted."))
            return False
        try:
            task = create_download_task(url, self.download_directory, audio_url=audio_url, subtitle_url=subtitle_url)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return False
        row = DownloadRow(self, url, task, audio_url=audio_url, subtitle_url=subtitle_url)
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
            and len(self._active_downloads) < self.max_concurrent_downloads
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

    def pause_download(self, row: DownloadRow) -> None:
        """Pause a queued or active direct HTTP transfer without losing its partial."""
        if not isinstance(row.task, DownloadTask):
            self.toast_overlay.add_toast(Adw.Toast.new("Pause is not available for FFmpeg stream downloads."))
            return
        if row in self._pending_downloads:
            self._pending_downloads.remove(row)
            row.finish("Paused")
            self._persist_queue()
            self._start_next_downloads()
            return
        if row in self._active_downloads:
            row.task.pause()
            row.status_label.set_text("Pausing…")
            row.pause_button.set_sensitive(False)
            row.cancel_button.set_sensitive(True)

    def retry_download(self, row: DownloadRow) -> None:
        if row in self._pending_downloads or row in self._active_downloads:
            return
        try:
            task = create_download_task(row.url, self.download_directory, audio_url=row.audio_url, subtitle_url=row.subtitle_url)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return
        row.prepare_retry(task)
        log_event(_LOG, "download_retry_queued", url=row.url)
        self._persist_queue()
        self._enqueue_download(row)
        self.toast_overlay.add_toast(Adw.Toast.new("Retry added to queue."))

    def _run_download(self, task: DownloadTask, row: DownloadRow) -> None:
        log_event(_LOG, "download_started", url=row.url)
        try:
            target = task.run(
                lambda progress: GLib.idle_add(row.update_progress, progress)
            )
            log_event(_LOG, "download_completed", url=row.url, destination=str(target))
            GLib.idle_add(self._download_finished, row, "Completed", str(target))
        except DownloadPaused as exc:
            log_event(_LOG, "download_paused", url=row.url)
            GLib.idle_add(self._download_finished, row, "Paused", str(exc))
        except DownloadError as exc:
            state = "Cancelled" if task.state == "cancelled" else "Failed"
            log_event(_LOG, "download_failed" if state == "Failed" else "download_cancelled", level=40 if state == "Failed" else 20, url=row.url, error=str(exc))
            GLib.idle_add(self._download_finished, row, state, str(exc))
        except Exception as exc:  # Keep an unexpected worker error from silently losing the queue row.
            log_event(_LOG, "download_unexpected_error", level=40, url=row.url, error=str(exc), error_type=type(exc).__name__)
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
        elif state == "Paused":
            self.toast_overlay.add_toast(Adw.Toast.new("Download paused. Resume to continue from the saved partial when supported."))
        self._persist_queue()
        self._start_next_downloads()
        return GLib.SOURCE_REMOVE


class MediaGrabApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        try:
            configure_logging(load_settings()["diagnostics_level"])
        except OSError:
            # Diagnostics must never prevent the download manager from starting.
            pass
        self.connect("activate", self._on_activate)
        self.connect("command-line", self._on_command_line)

    def _on_activate(self, app: Adw.Application) -> None:
        window = app.get_active_window()
        if window is None:
            window = MediaGrabWindow(application=app)
        window.present()

    def _on_command_line(self, app: Adw.Application, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        try:
            action, argument = parse_command(args)
        except ValueError as exc:
            command_line.print(f"{exc}\n")
            return 2

        if action == "activate":
            self._on_activate(app)
            return 0

        if action in {"list", "status"}:
            window = app.get_active_window()
            if not isinstance(window, MediaGrabWindow):
                window = MediaGrabWindow(application=app)
            rows = [
                {
                    "id": index,
                    "url": row._source_url,
                    "status": row.status_label.get_text(),
                }
                for index, row in enumerate(window._rows, start=1)
            ]
            if action == "list":
                command_line.print(json.dumps(rows, ensure_ascii=False) + "\n")
            else:
                counts = {
                    "total": len(rows),
                    "active": sum(row.is_active for row in window._rows),
                    "queued": sum(row.status_label.get_text() == "Queued" for row in window._rows),
                    "completed": sum(row.status_label.get_text() == "Completed" for row in window._rows),
                    "failed": sum(row.status_label.get_text() == "Failed" for row in window._rows),
                }
                command_line.print(json.dumps(counts, ensure_ascii=False) + "\n")
            return 0

        self._on_activate(app)
        window = app.get_active_window()
        if not isinstance(window, MediaGrabWindow):
            command_line.print("Could not access the MediaGrab window.\n")
            return 1

        if action in {"add-url", "add-candidate"}:
            assert argument is not None
            accepted = (
                window.add_candidate_url(argument)
                if action == "add-candidate"
                else window.add_download_url(argument)
            )
            return 0 if accepted else 2

        assert argument is not None
        row_id = int(argument)
        if row_id > len(window._rows):
            command_line.print(f"No queue item with ID {row_id}.\n")
            return 2
        row = window._rows[row_id - 1]
        if action == "pause":
            if not isinstance(row.task, DownloadTask):
                command_line.print("Pause is only supported for direct HTTP downloads.\n")
                return 2
            if row not in window._pending_downloads and row not in window._active_downloads:
                command_line.print(f"Queue item {row_id} is not active or queued.\n")
                return 2
            window.pause_download(row)
        elif action == "cancel":
            if row not in window._pending_downloads and row not in window._active_downloads:
                command_line.print(f"Queue item {row_id} is not active or queued.\n")
                return 2
            window.cancel_download(row)
        elif action in {"resume", "retry"}:
            if row in window._pending_downloads or row in window._active_downloads:
                command_line.print(f"Queue item {row_id} is already active or queued.\n")
                return 2
            if row.status_label.get_text() not in {"Failed", "Cancelled", "Interrupted", "Paused", "Detected"}:
                command_line.print(f"Queue item {row_id} cannot be resumed from its current state.\n")
                return 2
            window.retry_download(row)
        command_line.print(f"{action} requested for queue item {row_id}.\n")
        return 0


def main() -> int:
    app = MediaGrabApplication()
    return app.run(sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
