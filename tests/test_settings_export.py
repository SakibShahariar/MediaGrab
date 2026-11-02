"""Tests for versioned settings export and import."""

import json
from pathlib import Path

import pytest

from mediagrab.settings_store import export_settings, import_settings, load_settings, save_settings


def test_export_import_round_trip_supported_preferences(tmp_path: Path) -> None:
    source_settings = tmp_path / "source" / "settings.json"
    exported = tmp_path / "portable" / "settings.json"
    restored_settings = tmp_path / "restored" / "settings.json"
    preferences = {
        "download_directory": str(tmp_path / "Media"),
        "diagnostics_level": "DEBUG",
        "max_concurrent_downloads": 7,
        "notifications_enabled": False,
    }
    save_settings(preferences, source_settings)

    export_settings(exported, source_settings)
    payload = json.loads(exported.read_text(encoding="utf-8"))
    assert payload["format"] == "mediagrab-settings"
    assert payload["version"] == 1
    assert payload["settings"] == preferences

    import_settings(exported, restored_settings)
    assert load_settings(restored_settings) == preferences


def test_export_does_not_include_unknown_or_secret_fields(tmp_path: Path) -> None:
    source = tmp_path / "settings.json"
    exported = tmp_path / "export.json"
    save_settings({"download_directory": str(tmp_path / "Downloads")}, source)
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["access_token"] = "must-not-export"
    source.write_text(json.dumps(raw), encoding="utf-8")

    export_settings(exported, source)
    text = exported.read_text(encoding="utf-8")
    assert "access_token" not in text
    assert "must-not-export" not in text


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"format":"other","version":1,"settings":{}}',
        '{"format":"mediagrab-settings","version":99,"settings":{}}',
        '{"format":"mediagrab-settings","version":1,"settings":[]} ',
        '{"format":"mediagrab-settings","version":1,"settings":{"download_directory":"relative"}}',
        '{"format":"mediagrab-settings","version":1,"settings":{"download_directory":"/tmp","notifications_enabled":"false"}}',
    ],
)
def test_invalid_exports_are_rejected_without_changing_existing_settings(
    tmp_path: Path, payload: str
) -> None:
    current = tmp_path / "settings.json"
    exported = tmp_path / "import.json"
    original = {
        "download_directory": str(tmp_path / "Existing"),
        "diagnostics_level": "WARNING",
        "max_concurrent_downloads": 4,
        "notifications_enabled": True,
    }
    save_settings(original, current)
    exported.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        import_settings(exported, current)

    assert load_settings(current) == original
    assert not current.with_suffix(".json.bak").exists()


def test_import_creates_atomic_backup_of_previous_settings(tmp_path: Path) -> None:
    current = tmp_path / "settings.json"
    exported = tmp_path / "import.json"
    original = {
        "download_directory": str(tmp_path / "Original"),
        "diagnostics_level": "WARNING",
        "max_concurrent_downloads": 4,
        "notifications_enabled": True,
    }
    replacement = {
        "download_directory": str(tmp_path / "Replacement"),
        "diagnostics_level": "DEBUG",
        "max_concurrent_downloads": 6,
        "notifications_enabled": False,
    }
    save_settings(original, current)
    exported.write_text(json.dumps({
        "format": "mediagrab-settings",
        "version": 1,
        "settings": replacement,
    }), encoding="utf-8")

    import_settings(exported, current)

    backup = current.with_suffix(".json.bak")
    assert json.loads(backup.read_text(encoding="utf-8")) == original
    assert load_settings(current) == replacement
    assert not list(tmp_path.glob("*.tmp"))


def test_import_can_skip_settings_backup(tmp_path: Path) -> None:
    current = tmp_path / "settings.json"
    exported = tmp_path / "import.json"
    original = {"download_directory": str(tmp_path / "Original")}
    replacement = {"download_directory": str(tmp_path / "Replacement")}
    save_settings(original, current)
    exported.write_text(json.dumps({
        "format": "mediagrab-settings",
        "version": 1,
        "settings": replacement,
    }), encoding="utf-8")

    import_settings(exported, current, backup=False)

    assert load_settings(current)["download_directory"] == replacement["download_directory"]
    assert not current.with_suffix(".json.bak").exists()
