"""Tests for persistent download-folder preferences."""

import json
from pathlib import Path

import pytest

from mediagrab.settings_store import default_download_directory, load_settings, save_settings


def test_missing_or_corrupt_settings_use_downloads(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert load_settings(path)["download_directory"] == str(default_download_directory())
    path.write_text("{bad", encoding="utf-8")
    assert load_settings(path)["download_directory"] == str(default_download_directory())


def test_save_and_load_settings_atomically(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"
    selected = tmp_path / "My Downloads"
    save_settings({"download_directory": str(selected)}, path)
    assert load_settings(path)["download_directory"] == str(selected)
    assert json.loads(path.read_text(encoding="utf-8")) == {"download_directory": str(selected)}
    assert not list(path.parent.glob("*.tmp"))


def test_relative_or_empty_paths_are_rejected_or_safely_defaulted(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"download_directory": "../downloads"}), encoding="utf-8")
    assert load_settings(path)["download_directory"] == str(default_download_directory())
    with pytest.raises(ValueError, match="absolute path"):
        save_settings({"download_directory": "relative"}, path)
    with pytest.raises(ValueError, match="non-empty"):
        save_settings({"download_directory": ""}, path)


def test_unexpected_json_shape_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(["not", "a", "mapping"]), encoding="utf-8")
    assert load_settings(path)["download_directory"] == str(default_download_directory())
