from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediagrab.quality_preferences import (
    load_preferred_video_height,
    preferred_quality_index,
    save_preferred_video_height,
)


def test_preferred_video_height_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config" / "quality.json"
    assert load_preferred_video_height(path) is None
    save_preferred_video_height(1080, path)
    assert load_preferred_video_height(path) == 1080
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("height", [0, -1, 4321, True, "1080", 1080.0])
def test_invalid_preferred_video_height_is_rejected(tmp_path: Path, height) -> None:
    with pytest.raises(ValueError, match="preferred video height"):
        save_preferred_video_height(height, tmp_path / "quality.json")


def test_invalid_or_corrupt_preference_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "quality.json"
    path.write_text(json.dumps({"preferred_video_height": True}), encoding="utf-8")
    assert load_preferred_video_height(path) is None
    path.write_text("{broken", encoding="utf-8")
    assert load_preferred_video_height(path) is None


@pytest.mark.parametrize(
    ("heights", "preferred", "expected"),
    [
        ([None, 360, 720, 1080], None, 0),
        ([None, 360, 720, 1080], 1080, 3),
        ([None, 360, 720, 1440], 1080, 2),
        ([None, 1440, 2160], 1080, 1),
        ([None, None, 0], 1080, 0),
        ([None, 360, 720], True, 0),
    ],
)
def test_preferred_quality_index_uses_best_available_height(heights, preferred, expected):
    assert preferred_quality_index(heights, preferred) == expected
