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


SETTINGS_EXPORT_FORMAT = "mediagrab-settings"
SETTINGS_EXPORT_VERSION = 1


def _validated_settings(settings: dict[str, Any]) -> dict[str, str | int | bool]:
    """Validate and normalize the settings fields supported by this version."""
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
    return {
        "download_directory": str(directory),
        "diagnostics_level": diagnostics_level.upper(),
        "max_concurrent_downloads": max_concurrent,
        "notifications_enabled": notifications_enabled,
    }


def export_settings(destination: str | Path, settings_path: str | Path | None = None) -> None:
    """Export supported preferences without credentials or other secret material."""
    settings = load_settings(settings_path)
    payload = json.dumps({
        "format": SETTINGS_EXPORT_FORMAT,
        "version": SETTINGS_EXPORT_VERSION,
        "settings": settings,
    }, indent=2) + "\n"
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _backup_settings_file(settings_path: Path) -> Path | None:
    """Atomically preserve the current settings file beside it before replacement."""
    if not settings_path.is_file():
        return None
    backup_path = settings_path.with_suffix(settings_path.suffix + ".bak")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{backup_path.name}.", suffix=".tmp", dir=settings_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(settings_path.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, backup_path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return backup_path


def import_settings(
    source: str | Path,
    settings_path: str | Path | None = None,
    *,
    backup: bool = True,
) -> None:
    """Validate an export, back up current preferences, then replace them."""
    try:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("settings export is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("settings export must be a JSON object")
    if payload.get("format") != SETTINGS_EXPORT_FORMAT:
        raise ValueError("unrecognized settings export format")
    if payload.get("version") != SETTINGS_EXPORT_VERSION:
        raise ValueError("unsupported settings export version")
    raw_settings = payload.get("settings")
    if not isinstance(raw_settings, dict):
        raise ValueError("settings export must contain a settings object")
    validated = _validated_settings(raw_settings)
    target = Path(settings_path) if settings_path is not None else default_settings_path()
    if backup:
        _backup_settings_file(target)
    save_settings(validated, target)


def restore_settings_backup(settings_path: str | Path | None = None) -> dict[str, str | int | bool]:
    """Restore the validated adjacent backup without overwriting that backup."""
    target = Path(settings_path) if settings_path is not None else default_settings_path()
    backup_path = target.with_suffix(target.suffix + ".bak")
    try:
        raw: Any = json.loads(backup_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("settings backup is missing or unreadable") from exc
    if not isinstance(raw, dict):
        raise ValueError("settings backup must be a JSON object")
    validated = _validated_settings(raw)
    save_settings(validated, target)
    return validated
