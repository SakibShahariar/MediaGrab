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
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "download_directory": str(selected),
        "diagnostics_level": "INFO",
        "max_concurrent_downloads": 3,
    }
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


def test_default_settings_path_respects_xdg_config_home(monkeypatch, tmp_path: Path) -> None:
    from mediagrab.settings_store import default_settings_path
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert default_settings_path() == tmp_path / "config" / "mediagrab" / "settings.json"
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    assert default_settings_path() == Path.home() / ".config" / "mediagrab" / "settings.json"



def test_diagnostics_verbosity_is_validated_and_persisted(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert load_settings(path)["diagnostics_level"] == "INFO"
    save_settings({
        "download_directory": str(tmp_path / "Downloads"),
        "diagnostics_level": "DEBUG",
    }, path)
    assert load_settings(path)["diagnostics_level"] == "DEBUG"
    path.write_text(json.dumps({
        "download_directory": str(tmp_path / "Downloads"),
        "diagnostics_level": "TRACE",
    }), encoding="utf-8")
    assert load_settings(path)["diagnostics_level"] == "INFO"
    with pytest.raises(ValueError, match="diagnostics_level"):
        save_settings({
            "download_directory": str(tmp_path / "Downloads"),
            "diagnostics_level": "TRACE",
        }, path)



@pytest.mark.parametrize("limit", [1, 2, 3, 5, 10])
def test_max_concurrent_download_limit_is_persisted(tmp_path: Path, limit: int) -> None:
    path = tmp_path / "settings.json"
    save_settings({
        "download_directory": str(tmp_path / "Downloads"),
        "diagnostics_level": "INFO",
        "max_concurrent_downloads": limit,
    }, path)
    assert load_settings(path)["max_concurrent_downloads"] == limit


@pytest.mark.parametrize("limit", [0, 11, -1, True, "4", 2.5])
def test_invalid_max_concurrent_download_limit_is_rejected(tmp_path: Path, limit) -> None:
    path = tmp_path / "settings.json"
    with pytest.raises(ValueError, match="max_concurrent_downloads"):
        save_settings({
            "download_directory": str(tmp_path / "Downloads"),
            "diagnostics_level": "INFO",
            "max_concurrent_downloads": limit,
        }, path)


def test_legacy_settings_default_to_three_concurrent_downloads(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "download_directory": str(tmp_path / "Downloads"),
        "diagnostics_level": "DEBUG",
    }), encoding="utf-8")
    assert load_settings(path)["max_concurrent_downloads"] == 3


def test_invalid_saved_concurrency_falls_back_to_default(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "download_directory": str(tmp_path / "Downloads"),
        "max_concurrent_downloads": 100,
    }), encoding="utf-8")
    assert load_settings(path)["max_concurrent_downloads"] == 3
