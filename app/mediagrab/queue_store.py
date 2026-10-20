"""Crash-resistant persistence for unfinished download queue state."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

OPTIONAL_URL_FIELDS = ("audio_url", "subtitle_url")


def default_queue_path() -> Path:
    """Return the per-user state location, respecting XDG_STATE_HOME."""
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    state_home = Path(configured) if configured else Path.home() / ".local" / "state"
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


def load_queue(path: str | Path | None = None) -> list[dict[str, str]]:
    """Load valid entries, retaining optional track URLs and accepting old URL-only state."""
    queue_path = Path(path) if path is not None else default_queue_path()
    try:
        raw: Any = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []

    entries: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict) or not _valid_http_url(item.get("url")):
            continue
        entry = {"url": item["url"]}
        for field in OPTIONAL_URL_FIELDS:
            value = item.get(field)
            if value is None or value == "":
                continue
            if _valid_http_url(value):
                entry[field] = value
        entries.append(entry)
    return entries


def save_queue(entries: list[dict[str, str]], path: str | Path | None = None) -> None:
    """Atomically save unfinished entries, preserving valid optional track selections."""
    queue_path = Path(path) if path is not None else default_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    normalized: list[dict[str, str]] = []
    for item in entries:
        if not _valid_http_url(item.get("url")):
            continue
        entry = {"url": item["url"]}
        for field in OPTIONAL_URL_FIELDS:
            value = item.get(field)
            if value and _valid_http_url(value):
                entry[field] = value
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
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
