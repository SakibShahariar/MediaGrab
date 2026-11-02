"""Composable filtering for local download-history records."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_FILE_TYPES = {
    "Video": {".mp4", ".m4v", ".mkv", ".webm", ".mov", ".ogv", ".avi", ".mpeg", ".mpg"},
    "Audio": {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".weba"},
    "HLS/DASH": {".m3u8", ".mpd"},
    "Subtitles": {".vtt", ".srt", ".ass", ".ssa", ".ttml", ".dfxp"},
}


def matches_history_entry(
    entry: dict[str, Any],
    *,
    query: str = "",
    status: str = "All statuses",
    file_type: str = "All files",
    domain: str = "",
    since: datetime | None = None,
    size_filter: str = "Any size",
) -> bool:
    """Return whether a history record satisfies every supplied filter."""
    searchable = " ".join(str(value) for value in entry.values()).casefold()
    if query.strip().casefold() not in searchable:
        return False
    if status != "All statuses" and entry.get("outcome") != status:
        return False

    filename = str(entry.get("filename", ""))
    suffix = Path(filename).suffix.casefold()
    if file_type != "All files":
        if file_type == "Other":
            if any(suffix in extensions for extensions in _FILE_TYPES.values()):
                return False
        elif suffix not in _FILE_TYPES.get(file_type, set()):
            return False

    if domain.strip():
        try:
            hostname = (urlparse(str(entry.get("source_url", ""))).hostname or "").casefold()
        except ValueError:
            hostname = ""
        wanted = domain.strip().casefold().lstrip(".")
        if hostname != wanted and not hostname.endswith("." + wanted):
            return False

    if since is not None:
        try:
            timestamp = datetime.fromisoformat(str(entry.get("timestamp", "")).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.astimezone()
            cutoff = since
            if cutoff.tzinfo is None:
                cutoff = cutoff.astimezone()
            if timestamp < cutoff:
                return False
        except (TypeError, ValueError, OverflowError):
            return False

    size = entry.get("size")
    if size_filter == "Unknown size":
        if size is not None:
            return False
    elif size_filter == "Under 100 MB":
        if not isinstance(size, int) or isinstance(size, bool) or size >= 100 * 1024 * 1024:
            return False
    elif size_filter == "100 MB–1 GB":
        if not isinstance(size, int) or isinstance(size, bool) or not 100 * 1024 * 1024 <= size <= 1024 * 1024 * 1024:
            return False
    elif size_filter == "Over 1 GB":
        if not isinstance(size, int) or isinstance(size, bool) or size <= 1024 * 1024 * 1024:
            return False
    return True
