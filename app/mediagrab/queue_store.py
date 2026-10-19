"""Crash-resistant persistence for MediaGrab's unfinished download queue."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def default_queue_path() -> Path:
    """Return the per-user state location, respecting XDG_STATE_HOME."""
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "mediagrab" / "queue.json"


def load_queue(path: str | Path | None = None) -> list[dict[str, str]]:
    """Load valid queued items. Invalid or unreadable state safely becomes empty."""
    queue_path = Path(path) if path is not None else default_queue_path()
    try:
        raw: Any = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []

    entries: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        entries.append({"url": url})
    return entries


def save_queue(entries: list[dict[str, str]], path: str | Path | None = None) -> None:
    """Atomically save unfinished queue entries, creating the state directory."""
    queue_path = Path(path) if path is not None else default_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
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
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
