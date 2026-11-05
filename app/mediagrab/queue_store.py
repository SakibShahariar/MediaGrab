"""Crash-resistant persistence for unfinished download queue state."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mediagrab.checksum import parse_expected_checksum

OPTIONAL_URL_FIELDS = ("audio_url", "subtitle_url")
OUTPUT_FORMATS = {"mkv", "mp4"}
DASH_VIDEO_STREAM_INDEX_FIELD = "dash_video_stream_index"


def _valid_output_format(value: Any) -> bool:
    return isinstance(value, str) and value in OUTPUT_FORMATS


def _valid_dash_video_stream_index(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


QueueEntry = dict[str, Any]
_REPLACEMENT_SIGNATURE_FIELDS = ("device", "inode", "size", "mtime_ns")


def _valid_replacement_signature(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(_REPLACEMENT_SIGNATURE_FIELDS)
        and all(
            isinstance(value.get(field), int) and not isinstance(value.get(field), bool)
            for field in _REPLACEMENT_SIGNATURE_FIELDS
        )
    )




def default_queue_path() -> Path:
    """Return the per-user state location, respecting XDG_STATE_HOME."""
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    default_home = Path.home() / ".local" / "state"
    state_home = Path(configured).expanduser() if configured else default_home
    # XDG_STATE_HOME must be absolute; ignore invalid relative values rather
    # than writing application state relative to the current working directory.
    if not state_home.is_absolute():
        state_home = default_home
    return state_home / "mediagrab" / "queue.json"


def _valid_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(hostname) and not (
        parsed.username is not None or parsed.password is not None
    )



def _valid_checksum(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parse_expected_checksum(value)
    except ValueError:
        return False
    return True

def _fsync_directory(directory: Path) -> None:
    """Persist a directory entry update after an atomic rename."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_queue(path: str | Path | None = None) -> list[QueueEntry]:
    """Load valid entries, retaining optional track URLs and accepting old URL-only state."""
    queue_path = Path(path) if path is not None else default_queue_path()
    try:
        raw: Any = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []

    entries: list[QueueEntry] = []
    for item in raw:
        if not isinstance(item, dict) or not _valid_http_url(item.get("url")):
            continue
        entry: QueueEntry = {"url": item["url"]}
        for field in OPTIONAL_URL_FIELDS:
            value = item.get(field)
            if value is None or value == "":
                continue
            if _valid_http_url(value):
                entry[field] = value
        if item.get("candidate") is True:
            entry["candidate"] = True
        if item.get("interrupted_recorded") is True:
            entry["interrupted_recorded"] = True
        if _valid_checksum(item.get("expected_checksum")):
            entry["expected_checksum"] = item["expected_checksum"]
        if _valid_output_format(item.get("output_format")):
            entry["output_format"] = item["output_format"]
        if _valid_dash_video_stream_index(item.get(DASH_VIDEO_STREAM_INDEX_FIELD)):
            entry[DASH_VIDEO_STREAM_INDEX_FIELD] = item[DASH_VIDEO_STREAM_INDEX_FIELD]
        target = item.get("replacement_target")
        signature = item.get("replacement_signature")
        if isinstance(target, str) and target and _valid_replacement_signature(signature):
            entry["replacement_target"] = target
            entry["replacement_signature"] = signature
        entries.append(entry)
    return entries


def save_queue(entries: list[QueueEntry], path: str | Path | None = None) -> None:
    """Atomically save unfinished entries, preserving valid optional track selections."""
    queue_path = Path(path) if path is not None else default_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    normalized: list[QueueEntry] = []
    for item in entries:
        if not isinstance(item, dict) or not _valid_http_url(item.get("url")):
            continue
        entry: QueueEntry = {"url": item["url"]}
        for field in OPTIONAL_URL_FIELDS:
            value = item.get(field)
            if value and _valid_http_url(value):
                entry[field] = value
        if item.get("candidate") is True:
            entry["candidate"] = True
        if item.get("interrupted_recorded") is True:
            entry["interrupted_recorded"] = True
        if _valid_checksum(item.get("expected_checksum")):
            entry["expected_checksum"] = item["expected_checksum"]
        if _valid_output_format(item.get("output_format")):
            entry["output_format"] = item["output_format"]
        stream_index = item.get("dash_video_stream_index")
        if isinstance(stream_index, int) and not isinstance(stream_index, bool) and stream_index >= 0:
            entry["dash_video_stream_index"] = stream_index
        target = item.get("replacement_target")
        signature = item.get("replacement_signature")
        if isinstance(target, str) and target and _valid_replacement_signature(signature):
            entry["replacement_target"] = target
            entry["replacement_signature"] = signature
        normalized.append(entry)
    payload = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{queue_path.name}.", suffix=".tmp", dir=queue_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, queue_path)
        _fsync_directory(queue_path.parent)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
