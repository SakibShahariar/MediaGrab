"""Remember safe, non-destructive duplicate-resolution preferences."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

REMEMBERABLE_ACTIONS = frozenset({"keep-both", "skip"})


def default_preferences_path() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    config_home = Path(configured).expanduser() if configured else Path.home() / ".config"
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "mediagrab" / "duplicate-preferences.json"


def load_remembered_duplicate_action(path: str | Path | None = None) -> str | None:
    """Return a validated non-destructive choice, or None to ask every time."""
    target = Path(path) if path is not None else default_preferences_path()
    try:
        raw: Any = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    action = raw.get("action")
    return action if isinstance(action, str) and action in REMEMBERABLE_ACTIONS else None


def save_remembered_duplicate_action(action: str, path: str | Path | None = None) -> None:
    """Persist only Keep both or Skip; destructive replacement is never remembered."""
    if not isinstance(action, str) or action not in REMEMBERABLE_ACTIONS:
        raise ValueError("Only Keep both and Skip can be remembered")
    target = Path(path) if path is not None else default_preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"action": action}, output, indent=2)
            output.write(chr(10))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise



def clear_remembered_duplicate_action(path: str | Path | None = None) -> None:
    """Forget the remembered choice so the next duplicate prompts again."""
    target = Path(path) if path is not None else default_preferences_path()
    target.unlink(missing_ok=True)
