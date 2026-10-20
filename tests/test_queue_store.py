"""Tests for persisted download queue state."""

from __future__ import annotations

import json
from pathlib import Path

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
