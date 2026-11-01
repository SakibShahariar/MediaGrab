"""Private, bounded local history for completed and interrupted downloads."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mediagrab.url_utils import redact_url

MAX_HISTORY_ENTRIES = 1000
_REQUIRED_FIELDS = ("source_url", "filename", "destination", "outcome", "timestamp")
_CHECKSUM_STATES = {"not-requested", "passed", "failed", "incomplete"}


def default_history_path() -> Path:
    """Return the per-user XDG state path for download history."""
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    state_home = Path(configured).expanduser() if configured else Path.home() / ".local" / "state"
    if not state_home.is_absolute():
        state_home = Path.home() / ".local" / "state"
    return state_home / "mediagrab" / "history.json"


def load_history(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load valid history records; missing or corrupt history is treated as empty."""
    history_path = Path(path) if path is not None else default_history_path()
    try:
        raw: Any = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in raw[-MAX_HISTORY_ENTRIES:]:
        if not isinstance(item, dict):
            continue
        if any(not isinstance(item.get(field), str) for field in _REQUIRED_FIELDS):
            continue
        size = item.get("size")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            continue
        entries.append({
            "source_url": item["source_url"],
            "filename": item["filename"],
            "destination": item["destination"],
            "size": size,
            "outcome": item["outcome"],
            "timestamp": item["timestamp"],
            "checksum_status": (
                item.get("checksum_status")
                if item.get("checksum_status") in _CHECKSUM_STATES
                else "not-requested"
            ),
        })
    return entries


def append_history(entry: dict[str, Any], path: str | Path | None = None) -> None:
    """Atomically append one normalized record, retaining only the newest entries."""
    if not isinstance(entry, dict) or any(not isinstance(entry.get(field), str) for field in _REQUIRED_FIELDS):
        raise ValueError("History entry is missing required text fields")
    size = entry.get("size")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        raise ValueError("History size must be a non-negative integer or null")
    checksum_status = entry.get("checksum_status", "not-requested")
    if checksum_status not in _CHECKSUM_STATES:
        raise ValueError("checksum_status must be not-requested, passed, failed, or incomplete")
    normalized = {
        "source_url": redact_url(entry["source_url"]),
        "filename": entry["filename"],
        "destination": entry["destination"],
        "size": size,
        "outcome": entry["outcome"],
        "timestamp": entry["timestamp"],
        "checksum_status": checksum_status,
    }
    history_path = Path(path) if path is not None else default_history_path()
    history_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        history_path.parent.chmod(0o700)
    except OSError:
        pass
    entries = (load_history(history_path) + [normalized])[-MAX_HISTORY_ENTRIES:]
    payload = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{history_path.name}.", suffix=".tmp", dir=history_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, history_path)
        descriptor = os.open(history_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def make_history_entry(
    *, source_url: str, filename: str, destination: str, size: int | None,
    outcome: str, checksum_status: str = "not-requested"
) -> dict[str, Any]:
    """Create a timestamped record without retaining transfer credentials."""
    return {
        "source_url": source_url,
        "filename": filename,
        "destination": destination,
        "size": size,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checksum_status": checksum_status,
    }


def clear_history(path: str | Path | None = None) -> None:
    """Remove the local history file and sync its directory entry."""
    history_path = Path(path) if path is not None else default_history_path()
    try:
        history_path.unlink()
    except FileNotFoundError:
        return
    descriptor = os.open(history_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
