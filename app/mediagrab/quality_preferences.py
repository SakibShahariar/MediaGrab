from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from mediagrab.settings_store import default_settings_path


def default_quality_preferences_path() -> Path:
    return default_settings_path().with_name("quality-preferences.json")


def load_preferred_video_height(path: str | Path | None = None) -> int | None:
    target = Path(path) if path is not None else default_quality_preferences_path()
    try:
        raw: Any = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    height = raw.get("preferred_video_height") if isinstance(raw, dict) else None
    if isinstance(height, bool) or not isinstance(height, int) or not 1 <= height <= 4320:
        return None
    return height


def save_preferred_video_height(height: int, path: str | Path | None = None) -> None:
    if isinstance(height, bool) or not isinstance(height, int) or not 1 <= height <= 4320:
        raise ValueError("preferred video height must be an integer from 1 to 4320")
    target = Path(path) if path is not None else default_quality_preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"preferred_video_height": height}, output)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def preferred_quality_index(heights: list[int | None], preferred_height: int | None) -> int:
    """Choose the highest declared height at or below the saved preference."""
    if isinstance(preferred_height, bool) or not isinstance(preferred_height, int) or preferred_height < 1:
        return 0
    candidates = [(i, h) for i, h in enumerate(heights) if i > 0 and isinstance(h, int) and not isinstance(h, bool) and h > 0]
    if not candidates:
        return 0
    lower = [(i, h) for i, h in candidates if h <= preferred_height]
    if lower:
        return max(lower, key=lambda item: (item[1], -item[0]))[0]
    return min(candidates, key=lambda item: (item[1], item[0]))[0]
