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



def test_preference_save_fsyncs_file_and_parent_directory(tmp_path: Path, monkeypatch) -> None:
    import os
    import stat
    from mediagrab import quality_preferences

    calls = []
    original_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        calls.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        original_fsync(descriptor)

    monkeypatch.setattr(quality_preferences.os, "fsync", recording_fsync)
    target = tmp_path / "private" / "quality.json"
    save_preferred_video_height(720, target)

    assert calls == [False, True]
    assert target.parent.stat().st_mode & 0o077 == 0


def test_failed_replace_preserves_previous_quality_preference(tmp_path: Path, monkeypatch) -> None:
    from mediagrab import quality_preferences

    target = tmp_path / "quality.json"
    save_preferred_video_height(720, target)

    def fail_replace(_source, _destination) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(quality_preferences.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        save_preferred_video_height(1080, target)

    assert load_preferred_video_height(target) == 720
    assert not list(tmp_path.glob("*.tmp"))
