"""Composable filtering for local download-history records."""

from __future__ import annotations

from datetime import datetime
import json
import os
import tempfile
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
    category: str = "All categories",
) -> bool:
    """Return whether a history record satisfies every supplied filter."""
    searchable = " ".join(str(value) for value in entry.values()).casefold()
    if query.strip().casefold() not in searchable:
        return False
    if status != "All statuses" and entry.get("outcome") != status:
        return False
    if category != "All categories" and entry.get("category", "Uncategorized") != category:
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


_FILTER_PREFERENCES = {
    "query": "",
    "status": "All statuses",
    "file_type": "All files",
    "domain": "",
    "date_range": "Any time",
    "size_filter": "Any size",
    "category": "All categories",
}
_ALLOWED_FILTER_VALUES = {
    "status": {"All statuses", "Completed", "Failed", "Cancelled", "Paused"},
    "file_type": {"All files", "Video", "Audio", "HLS/DASH", "Subtitles", "Other"},
    "date_range": {"Any time", "Last 24 hours", "Last 7 days", "Last 30 days"},
    "size_filter": {"Any size", "Unknown size", "Under 100 MB", "100 MB–1 GB", "Over 1 GB"},
    "category": {"All categories", "Direct download", "HLS/DASH stream", "Uncategorized"},
}


def default_history_filter_path() -> Path:
    """Return the per-user XDG config path for the last-used history filters."""
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    config_home = Path(configured).expanduser() if configured else Path.home() / ".config"
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "mediagrab" / "history-filters.json"


def load_history_filter_preferences(path: str | Path | None = None) -> dict[str, str]:
    """Load a validated last-used filter combination; ignore corrupt preferences."""
    preferences = dict(_FILTER_PREFERENCES)
    try:
        raw = json.loads((Path(path) if path is not None else default_history_filter_path()).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return preferences
    if not isinstance(raw, dict):
        return preferences
    for key, allowed in _ALLOWED_FILTER_VALUES.items():
        value = raw.get(key)
        if isinstance(value, str) and value in allowed:
            preferences[key] = value
    for key, limit in (("query", 256), ("domain", 253)):
        value = raw.get(key)
        if isinstance(value, str):
            preferences[key] = value[:limit]
    return preferences


def save_history_filter_preferences(
    preferences: dict[str, str], path: str | Path | None = None
) -> None:
    """Atomically persist a validated last-used history filter combination."""
    normalized = dict(_FILTER_PREFERENCES)
    for key, allowed in _ALLOWED_FILTER_VALUES.items():
        value = preferences.get(key, normalized[key])
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"Invalid history filter preference: {key}")
        normalized[key] = value
    for key, limit in (("query", 256), ("domain", 253)):
        value = preferences.get(key, normalized[key])
        if not isinstance(value, str):
            raise ValueError(f"Invalid history filter preference: {key}")
        normalized[key] = value[:limit]

    destination = Path(path) if path is not None else default_history_filter_path()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(normalized, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
