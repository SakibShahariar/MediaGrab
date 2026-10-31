"""Persistent user preferences for MediaGrab."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_MAX_CONCURRENT_DOWNLOADS = 3
MIN_MAX_CONCURRENT_DOWNLOADS = 1
MAX_MAX_CONCURRENT_DOWNLOADS = 10


def default_download_directory() -> Path:
    """Use the conventional per-user Downloads folder."""
    return Path.home() / "Downloads"


def default_settings_path() -> Path:
    """Return the XDG-compliant per-user configuration path."""
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    config_home = Path(configured) if configured else Path.home() / ".config"
    return config_home / "mediagrab" / "settings.json"


def load_settings(path: str | Path | None = None) -> dict[str, str | int]:
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
    diagnostics_level = raw.get("diagnostics_level", "INFO")
    if not isinstance(diagnostics_level, str) or diagnostics_level.upper() not in {"ERROR", "WARNING", "INFO", "DEBUG"}:
        diagnostics_level = "INFO"
    max_concurrent = raw.get("max_concurrent_downloads", DEFAULT_MAX_CONCURRENT_DOWNLOADS)
    if (
        isinstance(max_concurrent, bool)
        or not isinstance(max_concurrent, int)
        or not MIN_MAX_CONCURRENT_DOWNLOADS <= max_concurrent <= MAX_MAX_CONCURRENT_DOWNLOADS
    ):
        max_concurrent = DEFAULT_MAX_CONCURRENT_DOWNLOADS
    notifications_enabled = raw.get("notifications_enabled", True)
    if not isinstance(notifications_enabled, bool):
        notifications_enabled = True
    return {
        "download_directory": str(candidate),
        "diagnostics_level": diagnostics_level.upper(),
        "max_concurrent_downloads": max_concurrent,
        "notifications_enabled": notifications_enabled,
    }


def save_settings(settings: dict[str, str | int], path: str | Path | None = None) -> None:
    """Atomically save the supported settings as a per-user JSON file."""
    destination = settings.get("download_directory")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("download_directory must be a non-empty path")
    directory = Path(destination).expanduser()
    if not directory.is_absolute():
        raise ValueError("download_directory must be an absolute path")

    diagnostics_level = settings.get("diagnostics_level", "INFO")
    if not isinstance(diagnostics_level, str) or diagnostics_level.upper() not in {"ERROR", "WARNING", "INFO", "DEBUG"}:
        raise ValueError("diagnostics_level must be ERROR, WARNING, INFO, or DEBUG")
    max_concurrent = settings.get("max_concurrent_downloads", DEFAULT_MAX_CONCURRENT_DOWNLOADS)
    if (
        isinstance(max_concurrent, bool)
        or not isinstance(max_concurrent, int)
        or not MIN_MAX_CONCURRENT_DOWNLOADS <= max_concurrent <= MAX_MAX_CONCURRENT_DOWNLOADS
    ):
        raise ValueError(
            "max_concurrent_downloads must be an integer between "
            f"{MIN_MAX_CONCURRENT_DOWNLOADS} and {MAX_MAX_CONCURRENT_DOWNLOADS}"
        )
    notifications_enabled = settings.get("notifications_enabled", True)
    if not isinstance(notifications_enabled, bool):
        raise ValueError("notifications_enabled must be a boolean")
    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "download_directory": str(directory),
        "diagnostics_level": diagnostics_level.upper(),
        "max_concurrent_downloads": max_concurrent,
        "notifications_enabled": notifications_enabled,
    }, indent=2) + "\n"
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
