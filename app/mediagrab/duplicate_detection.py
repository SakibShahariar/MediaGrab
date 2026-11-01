"""Small, side-effect-free helpers for avoiding duplicate queue entries."""
from __future__ import annotations

from collections.abc import Iterable


_PENDING_STATUSES = frozenset({
    "Queued",
    "Starting…",
    "Downloading…",
    "Cancelling…",
    "Pausing…",
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
