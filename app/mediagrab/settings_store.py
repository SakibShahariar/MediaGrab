"""Persistent user preferences for MediaGrab."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def default_download_directory() -> Path:
    """Use the conventional per-user Downloads folder."""
    return Path.home() / "Downloads"


def default_settings_path() -> Path:
    """Return the XDG-compliant per-user configuration path."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "mediagrab" / "settings.json"


def load_settings(path: str | Path | None = None) -> dict[str, str]:
    """Load validated preferences, falling back safely when absent or malformed."""
    settings_path = Path(path) if path is not None else default_settings_path()
    try:
        raw: Any = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    destination = raw.get("download_directory")
    if not isinstance(destination, str) or not destination.strip():
        destination = str(default_download_directory())
    candidate = Path(destination).expanduser()
    if not candidate.is_absolute():
        candidate = default_download_directory()
    return {"download_directory": str(candidate)}


def save_settings(settings: dict[str, str], path: str | Path | None = None) -> None:
    """Atomically save the supported settings as a per-user JSON file."""
    destination = settings.get("download_directory")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("download_directory must be a non-empty path")
    directory = Path(destination).expanduser()
    if not directory.is_absolute():
        raise ValueError("download_directory must be an absolute path")

    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"download_directory": str(directory)}, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{settings_path.name}.", suffix=".tmp", dir=settings_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, settings_path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
