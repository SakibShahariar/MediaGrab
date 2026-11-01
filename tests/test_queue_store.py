"""Tests for persisted download queue state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediagrab.queue_store import load_queue, save_queue


def test_save_and_load_queue(tmp_path: Path) -> None:
    path = tmp_path / "state" / "queue.json"
    entries = [{"url": "https://example.test/a.zip"}, {"url": "http://example.test/b.bin"}]

    save_queue(entries, path)

    assert load_queue(path) == entries
    assert not list(path.parent.glob("*.tmp"))


def test_missing_or_corrupt_state_returns_empty_queue(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    assert load_queue(path) == []
    path.write_text("{broken", encoding="utf-8")
    assert load_queue(path) == []


def test_invalid_entries_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(
        json.dumps([
            {"url": "https://example.test/good.zip"},
            {"url": "file:///etc/passwd"},
            {"url": 123},
            "not an object",
        ]),
        encoding="utf-8",
    )

    assert load_queue(path) == [{"url": "https://example.test/good.zip"}]


def test_non_list_state_returns_empty_queue(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"url": "https://example.test/a"}), encoding="utf-8")
    assert load_queue(path) == []


def test_optional_track_urls_survive_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    entries = [{
        "url": "https://cdn.example/video.m3u8",
        "audio_url": "https://cdn.example/audio/en.m3u8",
        "subtitle_url": "https://cdn.example/subs/en.m3u8",
    }]
    save_queue(entries, path)
    assert load_queue(path) == entries


def test_legacy_entries_load_and_invalid_track_urls_are_dropped(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(json.dumps([
        {"url": "https://cdn.example/video.m3u8"},
        {"url": "https://cdn.example/other.m3u8", "audio_url": "file:///etc/passwd", "subtitle_url": "https://user:pass@cdn.example/subs.m3u8"},
    ]), encoding="utf-8")
    assert load_queue(path) == [
        {"url": "https://cdn.example/video.m3u8"},
        {"url": "https://cdn.example/other.m3u8"},
    ]


def test_malformed_authority_is_ignored_during_recovery(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(json.dumps([{"url": "https://[malformed/file.bin"}, {"url": "https://example.test/good.bin"}]), encoding="utf-8")
    assert load_queue(path) == [{"url": "https://example.test/good.bin"}]


def test_default_queue_path_respects_xdg_state_home(monkeypatch, tmp_path: Path) -> None:
    from mediagrab.queue_store import default_queue_path
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert default_queue_path() == tmp_path / "state" / "mediagrab" / "queue.json"
    monkeypatch.setenv("XDG_STATE_HOME", "")
    assert default_queue_path() == Path.home() / ".local" / "state" / "mediagrab" / "queue.json"


def test_non_utf8_state_returns_empty_queue(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_bytes(b"\xff\xfe\xfa")
    assert load_queue(path) == []


def test_save_queue_skips_invalid_entries(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    entries = [
        {"url": "https://example.test/good.zip"},
        {"url": "file:///etc/passwd"},
        None,
        "not a mapping",
    ]
    save_queue(entries, path)
    assert load_queue(path) == [{"url": "https://example.test/good.zip"}]


def test_relative_xdg_state_home_falls_back_to_default(monkeypatch) -> None:
    from mediagrab.queue_store import default_queue_path

    monkeypatch.setenv("XDG_STATE_HOME", "relative-state")
    assert default_queue_path() == (
        Path.home() / ".local" / "state" / "mediagrab" / "queue.json"
    )


def test_save_queue_fsyncs_file_and_parent_directory(tmp_path: Path, monkeypatch) -> None:
    import os
    import stat

    from mediagrab import queue_store

    calls = []
    original_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        calls.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        original_fsync(descriptor)

    monkeypatch.setattr(queue_store.os, "fsync", recording_fsync)
    path = tmp_path / "private" / "queue.json"
    save_queue([{"url": "https://example.test/file.bin"}], path)

    assert calls == [False, True]
    assert path.parent.stat().st_mode & 0o077 == 0
    assert path.stat().st_mode & 0o077 == 0


def test_failed_atomic_replace_preserves_previous_queue_and_cleans_temp(
    tmp_path: Path, monkeypatch
) -> None:
    from mediagrab import queue_store

    path = tmp_path / "queue.json"
    path.write_text('[{"url":"https://example.test/old.bin"}]', encoding="utf-8")

    def fail_replace(_source, _destination) -> None:
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(queue_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated atomic replace failure"):
        save_queue([{"url": "https://example.test/new.bin"}], path)

    assert load_queue(path) == [{"url": "https://example.test/old.bin"}]
    assert not any(
        item.name.startswith(f".{path.name}.") and item.name.endswith(".tmp")
        for item in path.parent.iterdir()
    )


def test_candidate_review_state_survives_queue_persistence(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    entries = [
        {"url": "https://example.test/video.m3u8", "candidate": True},
        {"url": "https://example.test/file.mp4", "candidate": False},
        {"url": "https://example.test/other.mp4", "candidate": "yes"},
    ]
    save_queue(entries, path)
    assert load_queue(path) == [
        {"url": "https://example.test/video.m3u8", "candidate": True},
        {"url": "https://example.test/file.mp4"},
        {"url": "https://example.test/other.mp4"},
    ]


def test_expected_checksum_survives_queue_persistence_and_invalid_values_are_dropped(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    valid = "sha256:" + "a" * 64
    save_queue([
        {"url": "https://example.test/verified.bin", "expected_checksum": valid},
        {"url": "https://example.test/unverified.bin", "expected_checksum": "sha512:bad"},
    ], path)
    assert load_queue(path) == [
        {"url": "https://example.test/verified.bin", "expected_checksum": valid},
        {"url": "https://example.test/unverified.bin"},
    ]
