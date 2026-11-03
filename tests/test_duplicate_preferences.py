"""Tests for remembered duplicate-resolution choices."""

from pathlib import Path

import pytest

from mediagrab.duplicate_preferences import (
    load_remembered_duplicate_action,
    save_remembered_duplicate_action,
)


def test_remembers_keep_both_and_skip(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-preferences.json"
    save_remembered_duplicate_action("keep-both", path)
    assert load_remembered_duplicate_action(path) == "keep-both"
    save_remembered_duplicate_action("skip", path)
    assert load_remembered_duplicate_action(path) == "skip"


def test_does_not_allow_remembering_destructive_replace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Only Keep both and Skip"):
        save_remembered_duplicate_action("replace", tmp_path / "prefs.json")


def test_invalid_or_corrupt_preference_falls_back_to_asking(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-preferences.json"
    assert load_remembered_duplicate_action(path) is None
    path.write_text('{"action": "replace"}', encoding="utf-8")
    assert load_remembered_duplicate_action(path) is None
    path.write_text('{"action": []}', encoding="utf-8")
    assert load_remembered_duplicate_action(path) is None
    path.write_text("{broken", encoding="utf-8")
    assert load_remembered_duplicate_action(path) is None


def test_preference_file_is_private(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-preferences.json"
    save_remembered_duplicate_action("skip", path)
    assert path.stat().st_mode & 0o077 == 0



def test_clear_remembered_choice_returns_to_prompting(tmp_path: Path) -> None:
    from mediagrab.duplicate_preferences import clear_remembered_duplicate_action

    path = tmp_path / "duplicate-preferences.json"
    save_remembered_duplicate_action("skip", path)
    clear_remembered_duplicate_action(path)
    assert load_remembered_duplicate_action(path) is None
