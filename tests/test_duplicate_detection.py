"""Tests for pending and completed-file duplicate detection."""
from pathlib import Path

from mediagrab.duplicate_detection import (
    find_completed_file_duplicates,
    has_pending_duplicate,
)


def test_detects_exact_url_already_queued_or_active() -> None:
    entries = [
        ("https://example.test/a.bin", "Queued"),
        ("https://example.test/b.bin", "Downloading…"),
    ]
    assert has_pending_duplicate("https://example.test/a.bin", entries)
    assert has_pending_duplicate("https://example.test/b.bin", entries)


def test_ignores_completed_failed_and_detected_rows() -> None:
    entries = [
        ("https://example.test/a.bin", "Completed"),
        ("https://example.test/b.bin", "Failed"),
        ("https://example.test/c.bin", "Detected"),
        ("https://example.test/d.bin", "Paused"),
    ]
    assert not has_pending_duplicate("https://example.test/a.bin", entries)
    assert not has_pending_duplicate("https://example.test/b.bin", entries)
    assert not has_pending_duplicate("https://example.test/c.bin", entries)
    assert has_pending_duplicate("https://example.test/d.bin", entries)


def test_duplicate_detection_requires_exact_url_match() -> None:
    entries = [("https://example.test/a.bin?token=one", "Queued")]
    assert not has_pending_duplicate("https://example.test/a.bin?token=two", entries)
    assert not has_pending_duplicate("https://example.test/a.bin", entries)


def test_duplicate_detection_accepts_generators() -> None:
    entries = ((f"https://example.test/{name}", "Queued") for name in ("a", "b"))
    assert has_pending_duplicate("https://example.test/b", entries)


def test_finds_completed_file_when_name_and_recorded_size_match(tmp_path: Path) -> None:
    target = tmp_path / "video.mkv"
    target.write_bytes(b"saved media")
    entry = {
        "filename": "video.mkv",
        "destination": str(tmp_path),
        "size": len(b"saved media"),
        "outcome": "Completed",
    }

    assert find_completed_file_duplicates("video.mkv", [entry]) == [entry]


def test_ignores_missing_changed_incomplete_and_different_named_files(tmp_path: Path) -> None:
    target = tmp_path / "video.mkv"
    target.write_bytes(b"changed media")
    entries = [
        {
            "filename": "video.mkv",
            "destination": str(tmp_path),
            "size": 1,
            "outcome": "Completed",
        },
        {
            "filename": "video.mkv",
            "destination": str(tmp_path / "missing"),
            "size": 1,
            "outcome": "Completed",
        },
        {
            "filename": "video.mkv",
            "destination": str(tmp_path),
            "size": len(b"changed media"),
            "outcome": "Failed",
        },
        {
            "filename": "other.mkv",
            "destination": str(tmp_path),
            "size": len(b"changed media"),
            "outcome": "Completed",
        },
    ]

    assert find_completed_file_duplicates("video.mkv", entries) == []


def test_rejects_unsafe_filename_and_invalid_history_metadata(tmp_path: Path) -> None:
    entry = {
        "filename": "video.mkv",
        "destination": str(tmp_path),
        "size": 0,
        "outcome": "Completed",
    }
    (tmp_path / "video.mkv").write_bytes(b"")
    invalid = [
        entry,
        {**entry, "destination": None},
        {**entry, "size": True},
        {**entry, "size": -1},
    ]

    assert find_completed_file_duplicates("../video.mkv", [entry]) == []
    assert find_completed_file_duplicates("video.mkv", invalid) == [entry]
