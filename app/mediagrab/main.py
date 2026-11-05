"""GTK4/libadwaita UI for MediaGrab's basic download workflow."""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from mediagrab.downloader import DownloadError, DownloadPaused, DownloadProgress, DownloadTask, filename_from_url
from mediagrab.formatting import format_eta
from mediagrab.media_inspector import ManifestInspection, inspect_manifest, format_dash_representation_label
from mediagrab.capture import MediaKind, HLSVariant, classify_media
from mediagrab.task_factory import create_download_task
from mediagrab.queue_store import load_queue, save_queue
from mediagrab.history_store import append_history, make_history_entry, load_history, clear_history
from mediagrab.history_filter import matches_history_entry, load_history_filter_preferences, save_history_filter_preferences
from mediagrab.duplicate_detection import (
    has_pending_duplicate,
    find_completed_file_duplicates,
    find_completed_url_duplicates,
    capture_replace_signature,
    replace_completed_download,
)
from mediagrab.duplicate_preferences import (
    load_remembered_duplicate_action,
    save_remembered_duplicate_action,
    clear_remembered_duplicate_action,
)
from mediagrab.media_stream import MediaStreamTask
from mediagrab.quality_preferences import load_preferred_video_height, preferred_quality_index, save_preferred_video_height
from mediagrab.settings_store import export_settings, import_settings, load_settings, restore_settings_backup, save_settings
from mediagrab.diagnostics import configure_logging, get_logger, log_event, read_diagnostics
from mediagrab.url_utils import is_valid_http_url, redact_url
from mediagrab.cli import HELP_TEXT, parse_command
from mediagrab.dbus_api import register_dbus_api
from mediagrab.extractors import (
    ExtractedMedia,
    discover_media_candidates,
    release_extractor_worker,
    reserve_extractor_worker,
)
from mediagrab.shortcuts import COMMAND_PALETTE_ACTIONS, SHORTCUTS


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


def set_accessible_label(widget: Gtk.Widget, label: str) -> None:
    """Expose a concise name to assistive technology for icon-only controls."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


def format_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


class DownloadRow(Adw.ActionRow):
    """One queue item, including progress, cancellation, and retry controls."""

    def __init__(self, window: "MediaGrabWindow", url: str, task: DownloadTask, *, audio_url: str | None = None, subtitle_url: str | None = None, expected_checksum: str | None = None, replacement_target: str | None = None, replacement_signature: dict[str, int] | None = None) -> None:
        parsed = urlparse(url)
        title = parsed.path.rsplit("/", 1)[-1] or parsed.netloc or url
        super().__init__(title=title, subtitle=redact_url(url))
        self.window = window
        self.url = url
        self.audio_url = audio_url
        self.subtitle_url = subtitle_url
        self.expected_checksum = expected_checksum
        self.output_format = getattr(task, "output_format", None)
        self.dash_video_stream_index = getattr(task, "dash_video_stream_index", None)
        self.replacement_target = replacement_target
        self.replacement_signature = replacement_signature
        self.task = task
        self.output_path: Path | None = None
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
        set_accessible_label(self.progress, "Download progress")
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_size_request(120, -1)
        self.add_suffix(self.progress)

        self.retry_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.retry_button.set_tooltip_text("Retry or resume download")
        set_accessible_label(self.retry_button, "Retry or resume download")
        self.retry_button.add_css_class("flat")
        self.retry_button.set_visible(False)
        self.retry_button.connect("clicked", self._on_retry)
        self.add_suffix(self.retry_button)

        self.candidate_action_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.candidate_action_button.set_tooltip_text("Download detected media")
        set_accessible_label(self.candidate_action_button, "Download detected media")
        self.candidate_action_button.add_css_class("flat")
        self.candidate_action_button.set_visible(False)
        self.candidate_action_button.connect("clicked", self._on_candidate_action)
        self.add_suffix(self.candidate_action_button)

        self.dismiss_candidate_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        self.dismiss_candidate_button.set_tooltip_text("Dismiss detected media")
        set_accessible_label(self.dismiss_candidate_button, "Dismiss detected media")
        self.dismiss_candidate_button.add_css_class("flat")
        self.dismiss_candidate_button.set_visible(False)
        self.dismiss_candidate_button.connect("clicked", self._on_dismiss_candidate)
        self.add_suffix(self.dismiss_candidate_button)

        self.pause_button = Gtk.Button.new_from_icon_name("media-playback-pause-symbolic")
        self.pause_button.set_tooltip_text("Pause direct download")
        set_accessible_label(self.pause_button, "Pause direct download")
        self.pause_button.add_css_class("flat")
        self.pause_button.set_visible(isinstance(task, DownloadTask))
        self.pause_button.connect("clicked", self._on_pause)
        self.add_suffix(self.pause_button)

        self.cancel_button = Gtk.Button.new_from_icon_name("process-stop-symbolic")
        self.cancel_button.set_tooltip_text("Cancel download")
        set_accessible_label(self.cancel_button, "Cancel download")
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
        self._completed_count = 0
        self._pending_downloads: list[DownloadRow] = []
        self._active_downloads: set[DownloadRow] = set()
        settings = load_settings()
        self.download_directory = Path(settings["download_directory"])
        self.max_concurrent_downloads = int(settings["max_concurrent_downloads"])
        self.notifications_enabled = bool(settings["notifications_enabled"])

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)
        header.set_title_widget(Adw.WindowTitle(title="MediaGrab", subtitle="Downloads"))

        history_button = Gtk.Button(label="History")
        history_button.set_tooltip_text("Open download history (Ctrl+Shift+H)")
        history_button.connect("clicked", self._on_history_clicked)
        header.pack_start(history_button)

        diagnostics_button = Gtk.Button.new_from_icon_name("dialog-information-symbolic")
        diagnostics_button.set_tooltip_text("Settings and diagnostics")
        set_accessible_label(diagnostics_button, "Settings and diagnostics")
        diagnostics_button.add_css_class("flat")
        diagnostics_button.connect("clicked", self._on_diagnostics_clicked)
        header.pack_end(diagnostics_button)

        destination_button = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        destination_button.set_tooltip_text("Choose download folder")
        set_accessible_label(destination_button, "Choose download folder")
        destination_button.add_css_class("flat")
        destination_button.connect("clicked", self._on_choose_destination)
        header.pack_end(destination_button)

        add_button = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_button.set_tooltip_text("Add a download URL (Ctrl+N)")
        set_accessible_label(add_button, "Add a download URL")
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
        set_accessible_label(self.search_entry, "Search downloads")
        self.search_entry.set_placeholder_text("Search downloads")
        self.search_entry.set_tooltip_text("Search by filename or source URL (Ctrl+F)")
        self.search_entry.connect("search-changed", self._on_search_changed)
        content.append(self.search_entry)

        self.command_palette = Gtk.Popover()
        self.command_palette.set_position(Gtk.PositionType.BOTTOM)
        palette_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for label, action_name in COMMAND_PALETTE_ACTIONS:
            command_button = Gtk.Button(label=label)
            command_button.set_halign(Gtk.Align.FILL)
            command_button.connect("clicked", self._run_palette_action, action_name)
            palette_box.append(command_button)
        self.command_palette.set_child(palette_box)
        self.command_palette.set_parent(self.search_entry)

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

    def _run_palette_action(self, _button: Gtk.Button, action_name: str) -> None:
        self.command_palette.popdown()
        if action_name == "add-download":
            self._on_add_clicked(None)
        elif action_name == "focus-search":
            self.search_entry.grab_focus()
        elif action_name == "open-history":
            self._on_history_clicked(None)
        elif action_name == "open-diagnostics":
            self._on_diagnostics_clicked(None)
        elif action_name in {"toggle-focused-download", "retry-focused-download", "cancel-focused-download", "open-focused-file"}:
            self._run_focused_download_action(action_name)

    def _focused_download_row(self) -> DownloadRow | None:
        """Return the queue row containing the current keyboard focus."""
        widget = self.get_focus()
        while widget is not None:
            if isinstance(widget, DownloadRow):
                return widget
            widget = widget.get_parent()
        return None

    def _run_focused_download_action(self, action_name: str) -> None:
        row = self._focused_download_row()
        if row is None:
            self.toast_overlay.add_toast(Adw.Toast.new("Focus a download row or one of its controls first."))
            return
        state = row.status_label.get_text()
        if action_name == "toggle-focused-download":
            if row in self._pending_downloads or row in self._active_downloads:
                self.pause_download(row)
            elif state in {"Paused", "Interrupted"}:
                self.retry_download(row)
            else:
                self.toast_overlay.add_toast(Adw.Toast.new("This download cannot be paused or resumed in its current state."))
        elif action_name == "retry-focused-download":
            if state in {"Failed", "Cancelled", "Interrupted", "Paused"}:
                self.retry_download(row)
            else:
                self.toast_overlay.add_toast(Adw.Toast.new("Only a failed, cancelled, interrupted, or paused download can be retried."))
        elif action_name == "cancel-focused-download":
            if row in self._pending_downloads or row in self._active_downloads:
                self.cancel_download(row)
            else:
                self.toast_overlay.add_toast(Adw.Toast.new("This download is not queued or active."))
        elif action_name == "open-focused-file":
            if state != "Completed" or row.output_path is None or not row.output_path.is_file():
                self.toast_overlay.add_toast(Adw.Toast.new("The focused row has no completed file to open."))
                return
            try:
                Gio.AppInfo.launch_default_for_uri(row.output_path.as_uri(), None)
            except GLib.Error as exc:
                _LOG.warning("Could not open completed download: %s", exc)
                self.toast_overlay.add_toast(Adw.Toast.new("Could not open the completed file."))

    def _footer_text(self) -> str:
        return (
            f"Up to {self.max_concurrent_downloads} simultaneous downloads · "
            "HLS/DASH streams use FFmpeg · browser detections wait for your review"
        )

    def _on_history_clicked(self, _button: Gtk.Button | None) -> None:
        history_window = Adw.Window(
            title="Download history", transient_for=self, modal=True
        )
        history_window.set_default_size(760, 520)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(20)
        content.set_margin_end(20)
        history_window.set_content(content)

        preferences = load_history_filter_preferences()
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search = Gtk.SearchEntry()
        set_accessible_label(search, "Search download history")
        search.set_hexpand(True)
        search.set_placeholder_text("Search history by filename, URL, or destination")
        search.set_text(preferences["query"])
        toolbar.append(search)
        status_filter = Gtk.DropDown.new_from_strings([
            "All statuses", "Completed", "Failed", "Cancelled", "Paused"
        ])
        set_accessible_label(status_filter, "Filter history by outcome")
        status_filter.set_tooltip_text("Filter history by outcome")
        status_filter.set_selected(("All statuses", "Completed", "Failed", "Cancelled", "Paused").index(preferences["status"]))
        toolbar.append(status_filter)
        clear_button = Gtk.Button(label="Clear history")
        clear_button.add_css_class("destructive-action")
        toolbar.append(clear_button)
        content.append(toolbar)

        filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_type_filter = Gtk.DropDown.new_from_strings([
            "All files", "Video", "Audio", "HLS/DASH", "Subtitles", "Other"
        ])
        set_accessible_label(file_type_filter, "Filter history by file type")
        file_type_filter.set_hexpand(True)
        file_type_filter.set_tooltip_text("Filter by file type")
        file_type_filter.set_selected(("All files", "Video", "Audio", "HLS/DASH", "Subtitles", "Other").index(preferences["file_type"]))
        filter_bar.append(file_type_filter)
        date_filter = Gtk.DropDown.new_from_strings([
            "Any time", "Last 24 hours", "Last 7 days", "Last 30 days"
        ])
        set_accessible_label(date_filter, "Filter history by date")
        date_filter.set_hexpand(True)
        date_filter.set_tooltip_text("Filter by date")
        date_filter.set_selected(("Any time", "Last 24 hours", "Last 7 days", "Last 30 days").index(preferences["date_range"]))
        filter_bar.append(date_filter)
        category_filter = Gtk.DropDown.new_from_strings(["All categories", "Direct download", "HLS/DASH stream", "Uncategorized"])
        set_accessible_label(category_filter, "Filter history by category")
        category_filter.set_hexpand(True)
        category_filter.set_tooltip_text("Filter by download category")
        category_filter.set_selected(("All categories", "Direct download", "HLS/DASH stream", "Uncategorized").index(preferences["category"]))
        filter_bar.append(category_filter)
        size_filter = Gtk.DropDown.new_from_strings([
            "Any size", "Unknown size", "Under 100 MB", "100 MB–1 GB", "Over 1 GB"
        ])
        set_accessible_label(size_filter, "Filter history by file size")
        size_filter.set_hexpand(True)
        size_filter.set_tooltip_text("Filter by file size")
        size_filter.set_selected(("Any size", "Unknown size", "Under 100 MB", "100 MB–1 GB", "Over 1 GB").index(preferences["size_filter"]))
        filter_bar.append(size_filter)
        content.append(filter_bar)

        domain_filter = Gtk.Entry()
        set_accessible_label(domain_filter, "Filter history by source domain")
        domain_filter.set_placeholder_text("Filter by source domain (e.g. example.com)")
        domain_filter.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        domain_filter.set_text(preferences["domain"])
        content.append(domain_filter)

        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(list_box)
        content.append(scroller)
        rows: list[tuple[Adw.ActionRow, dict[str, object]]] = []

        def render_history() -> None:
            child = list_box.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                list_box.remove(child)
                child = following
            rows.clear()
            history = list(reversed(load_history()))
            if not history:
                list_box.set_placeholder(Gtk.Label(label="No download history yet."))
            else:
                list_box.set_placeholder(Gtk.Label(label="No matching downloads."))
            for item in history:
                subtitle = (
                    f'{item["outcome"]} · {item["timestamp"]} · '
                    f'{item["source_url"]} · {item["destination"]}'
                )
                row = Adw.ActionRow(title=item["filename"], subtitle=subtitle)
                rows.append((row, item))
                if item["outcome"] == "Completed":
                    target = Path(item["destination"]) / item["filename"]
                    if target.is_file():
                        open_button = Gtk.Button.new_from_icon_name("document-open-symbolic")
                        open_button.set_tooltip_text("Open downloaded file")
                        set_accessible_label(open_button, "Open downloaded file")
                        open_button.add_css_class("flat")
                        open_button.connect("clicked", lambda _button, path=target: self._open_history_file(path))
                        row.add_suffix(open_button)
                list_box.append(row)
            apply_filter()

        def apply_filter(*_args: object) -> None:
            date_options = (None, 1, 7, 30)
            selected_date = date_filter.get_selected()
            days = date_options[selected_date] if selected_date < len(date_options) else None
            cutoff = datetime.now().astimezone() - timedelta(days=days) if days else None
            statuses = ("All statuses", "Completed", "Failed", "Cancelled", "Paused")
            status_index = status_filter.get_selected()
            status_value = statuses[status_index] if status_index < len(statuses) else "All statuses"
            file_types = ("All files", "Video", "Audio", "HLS/DASH", "Subtitles", "Other")
            type_index = file_type_filter.get_selected()
            type_value = file_types[type_index] if type_index < len(file_types) else "All files"
            size_options = ("Any size", "Unknown size", "Under 100 MB", "100 MB–1 GB", "Over 1 GB")
            size_index = size_filter.get_selected()
            size_value = size_options[size_index] if size_index < len(size_options) else "Any size"
            categories = ("All categories", "Direct download", "HLS/DASH stream", "Uncategorized")
            category_index = category_filter.get_selected()
            category_value = categories[category_index] if category_index < len(categories) else "All categories"
            for row, item in rows:
                row.set_visible(matches_history_entry(
                    item,
                    query=search.get_text(),
                    status=status_value,
                    file_type=type_value,
                    domain=domain_filter.get_text(),
                    since=cutoff,
                    size_filter=size_value,
                    category=category_value,
                ))

        def confirm_clear(_button: Gtk.Button) -> None:
            confirmation = Adw.AlertDialog(
                heading="Clear download history?",
                body="This removes MediaGrab's local history records. Downloaded files will not be deleted.",
            )
            confirmation.add_response("cancel", "Cancel")
            confirmation.add_response("clear", "Clear history")
            confirmation.set_default_response("cancel")
            confirmation.set_close_response("cancel")
            confirmation.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)

            def on_confirmation(_dialog: Adw.AlertDialog, response: str) -> None:
                if response != "clear":
                    return
                try:
                    clear_history()
                except OSError as exc:
                    self.toast_overlay.add_toast(Adw.Toast.new(f"Could not clear history: {exc}"))
                    return
                render_history()
                self.toast_overlay.add_toast(Adw.Toast.new("Download history cleared."))

            confirmation.connect("response", on_confirmation)
            confirmation.present(history_window)

        search.connect("search-changed", apply_filter)
        status_filter.connect("notify::selected", apply_filter)
        file_type_filter.connect("notify::selected", apply_filter)
        date_filter.connect("notify::selected", apply_filter)
        size_filter.connect("notify::selected", apply_filter)
        category_filter.connect("notify::selected", apply_filter)
        domain_filter.connect("changed", apply_filter)
        clear_button.connect("clicked", confirm_clear)

        def save_filter_preferences(_window: Adw.Window) -> bool:
            status_options = ("All statuses", "Completed", "Failed", "Cancelled", "Paused")
            type_options = ("All files", "Video", "Audio", "HLS/DASH", "Subtitles", "Other")
            date_options = ("Any time", "Last 24 hours", "Last 7 days", "Last 30 days")
            size_options = ("Any size", "Unknown size", "Under 100 MB", "100 MB–1 GB", "Over 1 GB")
            category_options = ("All categories", "Direct download", "HLS/DASH stream", "Uncategorized")
            try:
                save_history_filter_preferences({
                    "query": search.get_text(),
                    "status": status_options[status_filter.get_selected()],
                    "file_type": type_options[file_type_filter.get_selected()],
                    "domain": domain_filter.get_text(),
                    "date_range": date_options[date_filter.get_selected()],
                    "size_filter": size_options[size_filter.get_selected()],
                    "category": category_options[category_filter.get_selected()],
                })
            except (OSError, ValueError) as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save history filters: {exc}"))
            return False

        history_window.connect("close-request", save_filter_preferences)
        render_history()
        history_window.present()

    def _open_history_file(self, path: Path) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(str(path)).get_uri(), None
            )
        except GLib.Error as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Could not open downloaded file: {exc}"))

    def _on_diagnostics_clicked(self, _button: Gtk.Button) -> None:
        settings = load_settings()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(6)
        content.set_margin_bottom(6)
        content.set_margin_start(6)
        content.set_margin_end(6)
        content.append(Gtk.Label(label="Logging verbosity", xalign=0))
        level = Gtk.DropDown(model=Gtk.StringList.new(list(_DIAGNOSTIC_LEVELS)))
        set_accessible_label(level, "Logging verbosity")
        level.set_selected(_DIAGNOSTIC_LEVELS.index(settings["diagnostics_level"]))
        content.append(level)
        concurrency_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        concurrency_label = Gtk.Label(label="Maximum simultaneous downloads", xalign=0)
        concurrency_label.set_hexpand(True)
        concurrency = Gtk.SpinButton.new_with_range(1, 10, 1)
        set_accessible_label(concurrency, "Maximum simultaneous downloads")
        concurrency.set_value(int(settings["max_concurrent_downloads"]))
        concurrency_row.append(concurrency_label)
        concurrency_row.append(concurrency)
        content.append(concurrency_row)
        notifications = Gtk.CheckButton(label="Enable desktop notifications")
        notifications.set_active(bool(settings["notifications_enabled"]))
        content.append(notifications)
        forget_duplicate_choice = Gtk.Button(label="Forget remembered duplicate choice")
        forget_duplicate_choice.add_css_class("flat")

        def forget_duplicate_preference(_button: Gtk.Button) -> None:
            try:
                clear_remembered_duplicate_action()
            except OSError as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not forget duplicate choice: {exc}"))
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Remembered duplicate choice cleared."))
        forget_duplicate_choice.connect("clicked", forget_duplicate_preference)
        content.append(forget_duplicate_choice)
        copy_button = Gtk.Button(label="Copy redacted diagnostics")
        copy_button.add_css_class("flat")
        copy_button.connect("clicked", self._on_copy_diagnostics)
        content.append(copy_button)
        settings_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        export_button = Gtk.Button(label="Export settings…")
        export_button.connect("clicked", self._on_export_settings)
        import_button = Gtk.Button(label="Import settings…")
        import_button.connect("clicked", self._on_import_settings)
        restore_button = Gtk.Button(label="Restore previous backup")
        restore_button.connect("clicked", self._on_restore_settings_backup)
        settings_actions.append(export_button)
        settings_actions.append(import_button)
        settings_actions.append(restore_button)
        content.append(settings_actions)

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
                    "notifications_enabled": notifications.get_active(),
                })
                configure_logging(diagnostics_level)
                self.max_concurrent_downloads = concurrency.get_value_as_int()
                self.notifications_enabled = notifications.get_active()
                self.footer_label.set_text(self._footer_text())
                self._start_next_downloads()
            except (OSError, ValueError) as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save diagnostics settings: {exc}"))
                return
            self.toast_overlay.add_toast(Adw.Toast.new(f"Diagnostics verbosity set to {diagnostics_level}."))
        dialog.connect("response", on_response)
        dialog.present(self)

    def _choose_settings_file(self, *, save: bool) -> None:
        chooser = Gtk.FileChooserNative.new(
            "Export MediaGrab settings" if save else "Import MediaGrab settings",
            self,
            Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN,
            "Export" if save else "Import",
            "Cancel",
        )
        if save:
            chooser.set_current_name("mediagrab-settings.json")

        def on_response(dialog: Gtk.FileChooserNative, response: int) -> None:
            if response != Gtk.ResponseType.ACCEPT:
                return
            selected = dialog.get_file()
            path = selected.get_path() if selected is not None else None
            if not path:
                self.toast_overlay.add_toast(Adw.Toast.new("Choose a local settings file."))
                return
            try:
                if save:
                    export_settings(path)
                    message = "Settings exported."
                else:
                    import_settings(path)
                    settings = load_settings()
                    self.download_directory = Path(settings["download_directory"])
                    self.max_concurrent_downloads = int(settings["max_concurrent_downloads"])
                    self.notifications_enabled = bool(settings["notifications_enabled"])
                    configure_logging(settings["diagnostics_level"])
                    self.destination_label.set_text(f"Files are saved to {self.download_directory}")
                    self.footer_label.set_text(self._footer_text())
                    self._start_next_downloads()
                    message = "Settings imported; a local backup was saved when previous settings existed."
            except (OSError, ValueError) as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not {'export' if save else 'import'} settings: {exc}"))
                return
            self.toast_overlay.add_toast(Adw.Toast.new(message))

        chooser.connect("response", on_response)
        chooser.show()

    def _on_export_settings(self, _button: Gtk.Button) -> None:
        self._choose_settings_file(save=True)

    def _on_import_settings(self, _button: Gtk.Button) -> None:
        self._choose_settings_file(save=False)

    def _on_restore_settings_backup(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Restore previous settings?",
            body="This replaces current preferences with the local backup created before the last settings import.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("restore", "Restore")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "restore":
                return
            try:
                settings = restore_settings_backup()
                self.download_directory = Path(settings["download_directory"])
                self.max_concurrent_downloads = int(settings["max_concurrent_downloads"])
                self.notifications_enabled = bool(settings["notifications_enabled"])
                configure_logging(settings["diagnostics_level"])
                self.destination_label.set_text(f"Files are saved to {self.download_directory}")
                self.footer_label.set_text(self._footer_text())
                self._start_next_downloads()
            except (OSError, ValueError) as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not restore settings backup: {exc}"))
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Previous settings restored."))

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
                    "notifications_enabled": settings["notifications_enabled"],
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
                task = create_download_task(url, self.download_directory, audio_url=entry.get("audio_url"), subtitle_url=entry.get("subtitle_url"), expected_checksum=entry.get("expected_checksum"), output_format=entry.get("output_format", "mkv"), dash_video_stream_index=entry.get("dash_video_stream_index"))
            except ValueError:
                continue
            row = DownloadRow(
                self, url, task,
                audio_url=entry.get("audio_url"),
                subtitle_url=entry.get("subtitle_url"),
                expected_checksum=entry.get("expected_checksum"),
                replacement_target=entry.get("replacement_target"),
                replacement_signature=entry.get("replacement_signature"),
            )
            is_candidate = entry.get("candidate") is True
            row.finish("Detected" if is_candidate else "Interrupted")
            if not is_candidate and entry.get("interrupted_recorded") is not True:
                parsed = urlparse(url)
                try:
                    append_history(make_history_entry(
                        source_url=redact_url(url),
                        filename=Path(parsed.path).name or parsed.netloc or "download",
                        destination=str(self.download_directory),
                        size=None,
                        outcome="Interrupted",
                        checksum_status="incomplete" if entry.get("expected_checksum") else "not-requested",
                    ))
                except (OSError, ValueError) as exc:
                    _LOG.warning("Could not record interrupted download: %s", exc)
            self._rows.append(row)
            self.list_box.append(row)
        self._update_count()
        self._persist_queue()

    def _update_count(self) -> None:
        count = len(self._rows)
        self.count_label.set_text(f"{count} item" + ("" if count == 1 else "s"))
        self.clear_completed_button.set_sensitive(self._completed_count > 0)

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        query = self.search_entry.get_text().strip().casefold()
        for row in self._rows:
            status = row.status_label.get_text().casefold()
            row.set_visible(not query or query in row._search_text or query in status)

    def _on_clear_completed(self, _button: Gtk.Button) -> None:
        # Partition once instead of repeatedly calling list.remove(), which
        # scans the remaining queue for every completed row (quadratic work).
        completed: list[DownloadRow] = []
        remaining: list[DownloadRow] = []
        for row in self._rows:
            if row.status_label.get_text() == "Completed":
                completed.append(row)
            else:
                remaining.append(row)
        if not completed:
            return
        self._rows = remaining
        self._completed_count -= len(completed)
        for row in completed:
            self.list_box.remove(row)
        self._update_count()
        self._persist_queue()
        self.toast_overlay.add_toast(Adw.Toast.new(
            f"Removed {len(completed)} completed download" + ("" if len(completed) == 1 else "s") + " from the list."
        ))

    def _persist_queue(self) -> None:
        # Completed items are history only; unfinished items are restored as retryable.
        entries: list[dict[str, str | bool | int]] = []
        for row in self._rows:
            state = row.status_label.get_text()
            if state == "Completed":
                continue
            entry: dict[str, str | bool] = {
                "url": row.url,
                **({"audio_url": row.audio_url} if row.audio_url else {}),
                **({"subtitle_url": row.subtitle_url} if row.subtitle_url else {}),
                **({"expected_checksum": row.expected_checksum} if row.expected_checksum else {}),
                **({"output_format": row.output_format} if row.output_format else {}),
                **({"dash_video_stream_index": row.dash_video_stream_index} if row.dash_video_stream_index is not None else {}),
            }
            if state == "Detected":
                entry["candidate"] = True
            if state == "Interrupted":
                entry["interrupted_recorded"] = True
            if row.replacement_target and row.replacement_signature:
                entry["replacement_target"] = row.replacement_target
                entry["replacement_signature"] = row.replacement_signature
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

    def _on_add_clicked(self, _button: Gtk.Button | None) -> None:
        dialog = Adw.AlertDialog(
            heading="Add a download",
            body=f"Enter a direct file URL or an HLS/DASH manifest URL. The file will be saved in {self.download_directory}. HLS/DASH downloads require FFmpeg.",
        )
        entry = Gtk.Entry()
        set_accessible_label(entry, "Download URL")
        entry.set_placeholder_text("https://example.com/file.zip")
        checksum_entry = Gtk.Entry()
        set_accessible_label(checksum_entry, "Optional checksum")
        checksum_entry.set_placeholder_text("Optional checksum: sha256:… / sha1:… / md5:…")
        entry.set_hexpand(True)
        paste_button = Gtk.Button(label="Paste")
        paste_button.set_tooltip_text("Read a URL from the clipboard")
        paste_button.add_css_class("flat")
        paste_button.connect("clicked", self._on_paste_clipboard, entry)
        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        entry_row.append(entry)
        entry_row.append(paste_button)
        dialog_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        dialog_content.append(entry_row)
        dialog_content.append(checksum_entry)
        dialog.set_extra_child(dialog_content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("inspect", "Inspect media…")
        dialog.add_response("add", "Download")
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_add_response, entry, checksum_entry)
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
        self, _dialog: Adw.AlertDialog, response: str, entry: Gtk.Entry,
        checksum_entry: Gtk.Entry,
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
        self.add_download_url(url, expected_checksum=checksum_entry.get_text().strip() or None)

    def inspect_media_url(self, url: str) -> None:
        """Inspect a manifest off the GTK thread, then offer available HLS qualities."""
        if not is_valid_http_url(url):
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid credential-free HTTP(S) URL."))
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
        choice_heights: list[int | None] = [None]
        choice_dash_stream_indices: list[int | None] = [None]
        if result.kind is MediaKind.HLS:
            variants = sorted(result.variants, key=lambda item: (item.height or 0, item.bandwidth or 0))
            for variant in variants:
                choices.append((self._variant_label(variant), variant.url))
                choice_heights.append(variant.height)
                choice_dash_stream_indices.append(None)
        elif result.kind is MediaKind.DASH:
            # A representation is independently downloadable only when the
            # manifest declares a direct/inherited BaseURL. SegmentTemplate,
            # SegmentTimeline, and SegmentList entries need a segment-aware
            # downloader and must not be presented as direct file URLs.
            for representation in sorted(
                result.representations,
                key=lambda item: (item.height or 0, item.bandwidth or 0),
            ):
                if representation.url:
                    choices.append((
                        format_dash_representation_label(representation),
                        representation.url,
                    ))
                    choice_heights.append(representation.height)
                    choice_dash_stream_indices.append(None)
                elif (
                    representation.stream_index is not None
                    and representation.mime_type
                    and representation.mime_type.startswith("video/")
                    and representation.mpd_type == "static"
                ):
                    choices.append((
                        format_dash_representation_label(representation),
                        original_url,
                    ))
                    choice_heights.append(representation.height)
                    choice_dash_stream_indices.append(representation.stream_index)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(content, "set_margin_" + side)(6)
        if len(choices) > 1:
            dropdown = Gtk.DropDown(model=Gtk.StringList.new([label for label, _url in choices]))
            set_accessible_label(dropdown, "Download quality")
            dropdown.set_selected(preferred_quality_index(choice_heights, load_preferred_video_height()))
            content.append(Gtk.Label(label="Download choice", xalign=0))
            content.append(dropdown)
        else:
            dropdown = None
            content.append(Gtk.Label(label="No separate quality variants were declared. The original manifest will be queued.", wrap=True))

        output_format_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new(["MKV (default)", "MP4"])
        )
        set_accessible_label(output_format_dropdown, "Video output container")
        output_format_dropdown.set_selected(0)
        content.append(Gtk.Label(label="Output container", xalign=0))
        content.append(output_format_dropdown)
        content.append(Gtk.Label(
            label="This applies to FFmpeg-backed manifest downloads. Direct media files keep their original format.",
            xalign=0, wrap=True,
        ))

        def update_output_format_availability(*_args: object) -> None:
            choice_index = dropdown.get_selected() if dropdown is not None else 0
            choice_index = min(choice_index, len(choices) - 1)
            selected_url = choices[choice_index][1]
            is_stream = (
                selected_url == original_url
                or classify_media(selected_url) in {MediaKind.HLS, MediaKind.DASH}
            )
            output_format_dropdown.set_sensitive(is_stream)
            if not is_stream:
                output_format_dropdown.set_selected(0)

        if dropdown is not None:
            dropdown.connect("notify::selected", update_output_format_availability)
        update_output_format_availability()

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
                dash_video_stream_index = choice_dash_stream_indices[index]
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
                output_format = (
                    "mp4" if output_format_dropdown.get_sensitive()
                    and output_format_dropdown.get_selected() == 1 else "mkv"
                )
                if self.add_download_url(
                    chosen_video, audio_url=audio_url, subtitle_url=subtitle_url,
                    output_format=output_format,
                    dash_video_stream_index=dash_video_stream_index,
                ):
                    selected_height = choice_heights[index]
                    if selected_height is not None:
                        try:
                            save_preferred_video_height(selected_height)
                        except (OSError, ValueError) as exc:
                            _LOG.warning("Could not save preferred video quality: %s", exc)
                            self.toast_overlay.add_toast(Adw.Toast.new("Download added, but the quality preference could not be saved."))
                    self.dismiss_candidate_by_url(original_url)

        audio_choices = [item for item in result.renditions if item.kind == "audio" and item.url]
        subtitle_choices = [item for item in result.renditions if item.kind == "subtitles" and item.url]
        audio_dropdown = None
        subtitle_dropdown = None
        if audio_choices:
            content.append(Gtk.Label(label="Alternate audio (optional)", xalign=0))
            audio_labels = ["Use variant/default audio"] + [(item.name or item.language or "Audio track") + ((" · " + item.language) if item.language else "") + ((" · group " + item.group_id) if item.group_id else "") for item in audio_choices]
            audio_dropdown = Gtk.DropDown(model=Gtk.StringList.new(audio_labels))
            set_accessible_label(audio_dropdown, "Alternate audio track")
            content.append(audio_dropdown)
        if subtitle_choices:
            content.append(Gtk.Label(label="Subtitles (optional)", xalign=0))
            subtitle_labels = ["No extra subtitles"] + [(item.name or item.language or "Subtitle track") + ((" · " + item.language) if item.language else "") + ((" · group " + item.group_id) if item.group_id else "") for item in subtitle_choices]
            subtitle_dropdown = Gtk.DropDown(model=Gtk.StringList.new(subtitle_labels))
            set_accessible_label(subtitle_dropdown, "Subtitle track")
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
        if reserve_extractor_worker():
            worker = threading.Thread(
                target=self._discover_plugin_candidates,
                args=(url,),
                daemon=True,
                name="mediagrab-site-extractors",
            )
            try:
                worker.start()
            except RuntimeError:
                release_extractor_worker()
                _LOG.warning("Could not start the site extractor worker.")
        return True

    def _discover_plugin_candidates(self, source_url: str) -> None:
        """Run optional site extractors off the GTK thread in a bounded worker slot."""
        try:
            candidates = discover_media_candidates(source_url)
            if candidates:
                GLib.idle_add(self._append_extracted_candidates, candidates)
        finally:
            release_extractor_worker()

    def _append_extracted_candidates(self, candidates: list[ExtractedMedia]) -> bool:
        added = 0
        for candidate in candidates:
            if not is_valid_http_url(candidate.url):
                continue
            if any(row.url == candidate.url for row in self._rows):
                continue
            try:
                task = create_download_task(candidate.url, self.download_directory)
            except ValueError:
                continue
            row = DownloadRow(self, candidate.url, task)
            if candidate.title:
                row.set_title(candidate.title)
            row.finish("Detected")
            self._rows.append(row)
            self.list_box.append(row)
            added += 1
        if added:
            self._update_count()
            self._persist_queue()
            log_event(_LOG, "site_extractor_candidates_added", count=added)
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Site extractors found {added} additional candidate" + ("" if added == 1 else "s") + ".")
            )
        return GLib.SOURCE_REMOVE

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

    def add_download_url(
        self, url: str, *, audio_url: str | None = None,
        subtitle_url: str | None = None, expected_checksum: str | None = None,
        output_format: str = "mkv", dash_video_stream_index: int | None = None,
    ) -> bool:
        """Validate and enqueue a URL from either the UI or browser bridge."""
        if not is_valid_http_url(url):
            self.toast_overlay.add_toast(Adw.Toast.new("Enter a valid credential-free HTTP(S) URL."))
            return False
        if has_pending_duplicate(
            url,
            (
                (item.url, item.status_label.get_text())
                for item in self._rows
            ),
        ):
            self.toast_overlay.add_toast(
                Adw.Toast.new("This URL is already queued or downloading.")
            )
            return False
        try:
            task = create_download_task(url, self.download_directory, audio_url=audio_url, subtitle_url=subtitle_url, expected_checksum=expected_checksum, output_format=output_format, dash_video_stream_index=dash_video_stream_index)
        except ValueError as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(str(exc)))
            return False

        original_name = filename_from_url(url)
        if isinstance(task, MediaStreamTask):
            filename = f"{Path(original_name).stem or 'media'}.mkv"
        else:
            filename = original_name
        history = load_history()
        file_duplicates = find_completed_file_duplicates(
            filename, history, expected_checksum=expected_checksum
        )
        duplicates = list(file_duplicates)
        for entry in find_completed_url_duplicates(redact_url(url), history):
            if entry not in duplicates:
                duplicates.append(entry)
        if duplicates:
            remembered_action = load_remembered_duplicate_action()
            if remembered_action == "skip":
                self.toast_overlay.add_toast(Adw.Toast.new("Duplicate download skipped (remembered choice)."))
                return True
            if remembered_action == "keep-both":
                self._queue_new_download(
                    url, task,
                    audio_url=audio_url,
                    subtitle_url=subtitle_url,
                    expected_checksum=expected_checksum,
                )
                return True
            self._show_completed_duplicate_dialog(
                url, task, duplicates,
                audio_url=audio_url,
                subtitle_url=subtitle_url,
                expected_checksum=expected_checksum,
            )
            return True

        self._queue_new_download(
            url, task,
            audio_url=audio_url,
            subtitle_url=subtitle_url,
            expected_checksum=expected_checksum,
        )
        return True

    def _show_completed_duplicate_dialog(
        self,
        url: str,
        task: DownloadTask | MediaStreamTask,
        duplicates: list[dict[str, object]],
        *,
        audio_url: str | None = None,
        subtitle_url: str | None = None,
        expected_checksum: str | None = None,
    ) -> None:
        """Ask before downloading when history points to an unchanged completed file."""
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_top(6)
        content.set_margin_bottom(6)
        content.set_margin_start(6)
        content.set_margin_end(6)
        content.append(Gtk.Label(
            label="This URL has a completed download in history, or a saved file has a matching name and size. These are possible duplicate signals, not proof that the media contents are identical.",
            wrap=True,
            xalign=0,
        ))
        remember_choice = Gtk.CheckButton(
            label="Remember Keep both or Skip for future duplicate prompts"
        )
        content.append(remember_choice)
        for entry in duplicates[:4]:
            content.append(Gtk.Label(
                label=str(Path(str(entry["destination"])) / str(entry["filename"])),
                wrap=True,
                xalign=0,
                selectable=True,
            ))
        if len(duplicates) > 4:
            content.append(Gtk.Label(label=f"And {len(duplicates) - 4} more matching history entries.", xalign=0))

        dialog = Adw.AlertDialog(
            heading="Possible duplicate download",
            body="You can replace the existing file, keep both, skip this download, or cancel.",
        )
        dialog.set_extra_child(content)
        # Replacement is offered only for a file whose current size still
        # matches a completed-file history record. A URL-only history match
        # must never make an unrelated or changed path replaceable.
        candidate_paths = {
            str(Path(str(entry["destination"])) / str(entry["filename"]))
            for entry in file_duplicates
        }
        replacement_target = next(iter(candidate_paths)) if len(candidate_paths) == 1 else None
        replacement_signature = (
            capture_replace_signature(replacement_target)
            if replacement_target is not None else None
        )

        dialog.add_response("cancel", "Cancel")
        if replacement_target is not None and replacement_signature is not None:
            dialog.add_response("replace", "Replace existing")
            dialog.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("skip", "Skip download")
        dialog.add_response("download", "Keep both (new filename)")
        dialog.set_default_response("download")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)

        def response_cb(_dialog: Adw.AlertDialog, response: str) -> None:
            if response == "download":
                if remember_choice.get_active():
                    try:
                        save_remembered_duplicate_action("keep-both")
                    except OSError as exc:
                        self.toast_overlay.add_toast(Adw.Toast.new(f"Could not remember this choice: {exc}"))
                self._queue_new_download(
                    url, task,
                    audio_url=audio_url,
                    subtitle_url=subtitle_url,
                    expected_checksum=expected_checksum,
                )
            elif response == "replace" and replacement_target and replacement_signature:
                self._queue_new_download(
                    url, task,
                    audio_url=audio_url,
                    subtitle_url=subtitle_url,
                    expected_checksum=expected_checksum,
                    replacement_target=replacement_target,
                    replacement_signature=replacement_signature,
                )
            elif response == "skip":
                if remember_choice.get_active():
                    try:
                        save_remembered_duplicate_action("skip")
                    except OSError as exc:
                        self.toast_overlay.add_toast(Adw.Toast.new(f"Could not remember this choice: {exc}"))
                self.toast_overlay.add_toast(Adw.Toast.new("Duplicate download skipped."))

        dialog.connect("response", response_cb)
        dialog.present(self)

    def _queue_new_download(
        self,
        url: str,
        task: DownloadTask | MediaStreamTask,
        *,
        audio_url: str | None = None,
        subtitle_url: str | None = None,
        expected_checksum: str | None = None,
        replacement_target: str | None = None,
        replacement_signature: dict[str, int] | None = None,
    ) -> None:
        row = DownloadRow(
            self, url, task,
            audio_url=audio_url,
            subtitle_url=subtitle_url,
            expected_checksum=expected_checksum,
            replacement_target=replacement_target,
            replacement_signature=replacement_signature,
        )
        self._rows.append(row)
        self.list_box.append(row)
        self._update_count()
        self._persist_queue()
        self._enqueue_download(row)
        self.toast_overlay.add_toast(Adw.Toast.new("Added to download queue."))

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
            task = create_download_task(row.url, self.download_directory, audio_url=row.audio_url, subtitle_url=row.subtitle_url, expected_checksum=row.expected_checksum, output_format=row.output_format or "mkv", dash_video_stream_index=row.dash_video_stream_index)
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

    def _send_download_notification(self, row: DownloadRow, state: str, detail: str) -> None:
        if not self.notifications_enabled or state not in {"Completed", "Failed", "Paused"}:
            return
        application = self.get_application()
        if not isinstance(application, Gio.Application):
            return
        if state == "Completed":
            title = "Download completed"
            filename = Path(detail).name
            body = f"Saved {filename}."
        elif state == "Failed":
            title = "Download failed"
            body = "MediaGrab could not finish a download. Open the app to retry."
        else:
            title = "Download paused"
            body = "A download was paused. Open the app to resume it."

        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_default_action("app.show-window")
        if state == "Completed":
            target = Path(detail)
            if target.is_file():
                notification.add_button_with_target(
                    "Open file",
                    "app.open-file",
                    GLib.Variant.new_string(Gio.File.new_for_path(str(target)).get_uri()),
                )
        application.send_notification(f"mediagrab-download-{id(row)}", notification)

    def _download_finished(self, row: DownloadRow, state: str, detail: str) -> bool:
        row.is_active = False
        self._active_downloads.discard(row)
        if state == "Completed" and row.replacement_target and row.replacement_signature:
            try:
                replace_completed_download(detail, row.replacement_target, row.replacement_signature)
                detail = row.replacement_target
                log_event(_LOG, "duplicate_file_replaced", url=row.url, destination=detail)
            except (OSError, ValueError) as exc:
                log_event(_LOG, "duplicate_file_replace_skipped", level=30, url=row.url, error=str(exc))
                self.toast_overlay.add_toast(Adw.Toast.new(
                    f"Original file was preserved; the new copy was saved as {Path(detail).name}."
                ))
        if state == "Completed":
            row.output_path = Path(detail)
        row.finish(state, detail if state == "Failed" else None)
        if state in {"Completed", "Failed", "Cancelled", "Paused"}:
            if state == "Completed":
                target = Path(detail)
                filename = target.name
                destination = str(target.parent)
                try:
                    size = target.stat().st_size
                except OSError:
                    size = None
            else:
                parsed = urlparse(row.url)
                filename = Path(parsed.path).name or parsed.netloc or "download"
                destination = str(self.download_directory)
                size = None
            expected_checksum = getattr(row.task, "expected_checksum", None)
            if expected_checksum is None:
                checksum_status = "not-requested"
            elif state == "Completed":
                checksum_status = "passed"
            elif state == "Failed" and "checksum verification failed" in detail.casefold():
                checksum_status = "failed"
            else:
                checksum_status = "incomplete"
            try:
                append_history(make_history_entry(
                    source_url=redact_url(row.url),
                    filename=filename,
                    destination=destination,
                    size=size,
                    outcome=state,
                    checksum_status=checksum_status,
                    category=("HLS/DASH stream" if isinstance(row.task, MediaStreamTask) else "Direct download"),
                ))
            except (OSError, ValueError) as exc:
                _LOG.warning("Could not persist download history: %s", exc)
        if state == "Completed":
            self._completed_count += 1
        self._send_download_notification(row, state, detail)
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
        self.connect("startup", self._on_dbus_startup)
        self.connect("command-line", self._on_command_line)
        show_action = Gio.SimpleAction.new("show-window", None)
        show_action.connect("activate", lambda *_args: self._on_activate(self))
        self.add_action(show_action)
        open_action = Gio.SimpleAction.new("open-file", GLib.VariantType.new("s"))
        open_action.connect("activate", self._on_open_file)
        self.add_action(open_action)
        for action_name, accelerator in SHORTCUTS.items():
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", self._on_shortcut, action_name)
            self.add_action(action)
            self.set_accels_for_action(f"app.{action_name}", [accelerator])

    def _on_shortcut(
        self, _action: Gio.SimpleAction, _parameter: GLib.Variant | None,
        action_name: str,
    ) -> None:
        window = self.get_active_window()
        if not isinstance(window, MediaGrabWindow):
            self._on_activate(self)
            window = self.get_active_window()
        if not isinstance(window, MediaGrabWindow):
            return
        if action_name == "add-download":
            window._on_add_clicked(None)
        elif action_name == "focus-search":
            window.search_entry.grab_focus()
        elif action_name == "open-history":
            window._on_history_clicked(None)
        elif action_name == "open-diagnostics":
            window._on_diagnostics_clicked(None)
        elif action_name in {"toggle-focused-download", "retry-focused-download", "cancel-focused-download", "open-focused-file"}:
            window._run_focused_download_action(action_name)
        elif action_name == "open-command-palette":
            window.command_palette.popup()

    def _on_open_file(self, _action: Gio.SimpleAction, parameter: GLib.Variant | None) -> None:
        if parameter is None:
            return
        uri = parameter.get_string()
        file = Gio.File.new_for_uri(uri)
        if not uri.startswith("file://") or not file.query_exists(None):
            return
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as exc:
            _LOG.warning("Could not open completed download: %s", exc)

    def _on_activate(self, app: Adw.Application) -> None:
        window = app.get_active_window()
        if window is None:
            window = MediaGrabWindow(application=app)
        window.present()

    def _on_dbus_startup(self, _app: Adw.Application) -> None:
        try:
            register_dbus_api(self, Gio, GLib)
        except (GLib.Error, RuntimeError, ValueError) as exc:
            _LOG.warning("Could not export the public D-Bus API: %s", exc)

    def _execute_external_command(self, action: str, argument: str | None = None) -> str:
        """Execute one validated CLI/D-Bus operation through the same queue path."""
        if action == "help":
            return HELP_TEXT.rstrip()
        if action == "activate":
            self._on_activate(self)
            return "MediaGrab window activated."

        if action not in {"list", "status"}:
            self._on_activate(self)
        window = self.get_active_window()
        if not isinstance(window, MediaGrabWindow):
            window = MediaGrabWindow(application=self)

        if action in {"list", "status"}:
            rows = [
                {"id": index, "url": row._source_url, "status": row.status_label.get_text()}
                for index, row in enumerate(window._rows, start=1)
            ]
            if action == "list":
                return json.dumps(rows, ensure_ascii=False)
            counts = {
                "total": len(rows),
                "active": sum(row.is_active for row in window._rows),
                "queued": sum(row.status_label.get_text() == "Queued" for row in window._rows),
                "completed": sum(row.status_label.get_text() == "Completed" for row in window._rows),
                "failed": sum(row.status_label.get_text() == "Failed" for row in window._rows),
            }
            return json.dumps(counts, ensure_ascii=False)

        if action in {"add-url", "add-candidate"}:
            if argument is None:
                raise ValueError("A URL argument is required.")
            accepted = (
                window.add_candidate_url(argument)
                if action == "add-candidate"
                else window.add_download_url(argument)
            )
            if not accepted:
                raise ValueError("The URL was rejected or is already queued.")
            return f"{action} accepted."

        if argument is None:
            raise ValueError("A queue item ID is required.")
        try:
            row_id = int(argument)
        except (TypeError, ValueError) as exc:
            raise ValueError("Queue ID must be a positive integer.") from exc
        if row_id < 1:
            raise ValueError("Queue ID must be a positive integer.")
        if row_id > len(window._rows):
            raise LookupError(f"No queue item with ID {row_id}.")
        row = window._rows[row_id - 1]
        if action == "pause":
            if not isinstance(row.task, DownloadTask):
                raise ValueError("Pause is only supported for direct HTTP downloads.")
            if row not in window._pending_downloads and row not in window._active_downloads:
                raise RuntimeError(f"Queue item {row_id} is not active or queued.")
            window.pause_download(row)
        elif action == "cancel":
            if row not in window._pending_downloads and row not in window._active_downloads:
                raise RuntimeError(f"Queue item {row_id} is not active or queued.")
            window.cancel_download(row)
        elif action in {"resume", "retry"}:
            if row in window._pending_downloads or row in window._active_downloads:
                raise RuntimeError(f"Queue item {row_id} is already active or queued.")
            if row.status_label.get_text() not in {"Failed", "Cancelled", "Interrupted", "Paused", "Detected"}:
                raise RuntimeError(f"Queue item {row_id} cannot be resumed from its current state.")
            window.retry_download(row)
        else:
            raise ValueError(f"Unsupported operation: {action}")
        return f"{action} requested for queue item {row_id}."

    def _on_command_line(self, _app: Adw.Application, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        try:
            action, argument = parse_command(args)
            result = self._execute_external_command(action, argument)
        except (ValueError, LookupError, RuntimeError) as exc:
            command_line.print(f"{exc}\\n")
            return 2
        if action in {"help", "list", "status"}:
            command_line.print(result + "\\n")
        return 0


def main() -> int:
    app = MediaGrabApplication()
    return app.run(sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
