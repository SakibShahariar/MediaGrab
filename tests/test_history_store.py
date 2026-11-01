"""Tests for durable local download history."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediagrab.history_store import (
    MAX_HISTORY_ENTRIES,
    append_history,
    default_history_path,
    load_history,
    make_history_entry,
)


def _entry(index: int = 1):
    return make_history_entry(
        source_url=f"https://example.test/file-{index}.bin",
        filename=f"file-{index}.bin",
        destination=f"/home/user/Downloads/file-{index}.bin",
        size=123,
        outcome="Completed",
    )


def test_history_survives_restart_and_records_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "state" / "history.json"
    entry = _entry()

    append_history(entry, path)
    restored = load_history(path)

    assert len(restored) == 1
    assert restored[0]["source_url"] == entry["source_url"]
    assert restored[0]["size"] == 123
    assert restored[0]["outcome"] == "Completed"
    assert restored[0]["timestamp"]
    assert path.read_text(encoding="utf-8").endswith("\\n")
    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0
    assert not list(path.parent.glob("*.tmp"))


def test_history_is_bounded_to_newest_entries(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    for index in range(MAX_HISTORY_ENTRIES + 2):
        append_history(_entry(index), path)
    restored = load_history(path)
    assert len(restored) == MAX_HISTORY_ENTRIES
    assert restored[0]["filename"] == "file-2.bin"
    assert restored[-1]["filename"] == f"file-{MAX_HISTORY_ENTRIES + 1}.bin"


def test_missing_corrupt_and_non_list_history_load_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    assert load_history(path) == []
    path.write_text("{broken", encoding="utf-8")
    assert load_history(path) == []
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert load_history(path) == []


def test_invalid_records_are_ignored_and_invalid_appends_rejected(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text(json.dumps([_entry(), {"source_url": "missing fields"}, "bad"]), encoding="utf-8")
    assert len(load_history(path)) == 1
    with pytest.raises(ValueError, match="required text fields"):
        append_history({"source_url": "https://example.test"}, path)
    with pytest.raises(ValueError, match="non-negative integer"):
        append_history({**_entry(), "size": -1}, path)


def test_default_history_path_respects_xdg_state_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert default_history_path() == tmp_path / "state" / "mediagrab" / "history.json"
    monkeypatch.setenv("XDG_STATE_HOME", "relative")
    assert default_history_path() == Path.home() / ".local" / "state" / "mediagrab" / "history.json"
