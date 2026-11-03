"""Small, side-effect-free helpers for avoiding duplicate queue entries."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any


_PENDING_STATUSES = frozenset({
    "Queued",
    "Starting…",
    "Downloading…",
    "Cancelling…",
    "Pausing…",
    "Paused",
})


def has_pending_duplicate(
    url: str,
    entries: Iterable[tuple[str, str]],
) -> bool:
    """Return whether the exact URL already has a queued or active entry.

    Completed and failed entries are intentionally ignored so users can
    explicitly download the same resource again after an earlier attempt.
    """
    return any(
        existing_url == url and status in _PENDING_STATUSES
        for existing_url, status in entries
    )


def find_completed_file_duplicates(
    filename: str,
    history: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find completed history records whose saved file still matches its record.

    The recorded size is checked against the current file on disk. This only
    identifies candidates for a user-facing duplicate decision; matching a
    filename and historical size is not proof that two remote resources are
    byte-for-byte identical.
    """
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        return []

    matches: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict) or entry.get("outcome") != "Completed":
            continue
        if entry.get("filename") != filename:
            continue
        destination = entry.get("destination")
        recorded_size = entry.get("size")
        if (
            not isinstance(destination, str)
            or isinstance(recorded_size, bool)
            or not isinstance(recorded_size, int)
            or recorded_size < 0
        ):
            continue
        path = Path(destination) / filename
        try:
            if path.is_file() and path.stat().st_size == recorded_size:
                matches.append(entry)
        except OSError:
            continue
    return matches
