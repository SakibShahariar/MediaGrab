"""Tests for pending and completed-file duplicate detection."""

import hashlib
from pathlib import Path

import pytest

from mediagrab.duplicate_detection import (
    capture_replace_signature,
    find_completed_file_duplicates,
    has_pending_duplicate,
    replace_completed_download,
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
        {"filename": "video.mkv", "destination": str(tmp_path), "size": 1, "outcome": "Completed"},
        {"filename": "video.mkv", "destination": str(tmp_path / "missing"), "size": 1, "outcome": "Completed"},
        {"filename": "video.mkv", "destination": str(tmp_path), "size": len(b"changed media"), "outcome": "Failed"},
        {"filename": "other.mkv", "destination": str(tmp_path), "size": len(b"changed media"), "outcome": "Completed"},
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


def test_replaces_original_only_after_download_is_complete(tmp_path: Path) -> None:
    original = tmp_path / "video.mkv"
    downloaded = tmp_path / "video (1).mkv"
    original.write_bytes(b"old content")
    downloaded.write_bytes(b"new complete content")
    signature = capture_replace_signature(original)
    assert signature is not None

    replace_completed_download(downloaded, original, signature)

    assert original.read_bytes() == b"new complete content"
    assert not downloaded.exists()


def test_preserves_original_if_it_changes_after_confirmation(tmp_path: Path) -> None:
    original = tmp_path / "video.mkv"
    downloaded = tmp_path / "video (1).mkv"
    original.write_bytes(b"old content")
    downloaded.write_bytes(b"new content")
    signature = capture_replace_signature(original)
    assert signature is not None
    original.write_bytes(b"changed by user")

    with pytest.raises(OSError, match="original file changed"):
        replace_completed_download(downloaded, original, signature)

    assert original.read_bytes() == b"changed by user"
    assert downloaded.read_bytes() == b"new content"


def test_rejects_symlink_target_and_missing_download(tmp_path: Path) -> None:
    real = tmp_path / "real.mkv"
    link = tmp_path / "link.mkv"
    real.write_bytes(b"original")
    link.symlink_to(real)
    assert capture_replace_signature(link) is None

    signature = capture_replace_signature(real)
    assert signature is not None
    with pytest.raises(OSError, match="completed download is missing"):
        replace_completed_download(tmp_path / "missing.mkv", real, signature)
    assert real.read_bytes() == b"original"


def test_rechecks_original_after_staging_download(tmp_path: Path, monkeypatch) -> None:
    from mediagrab import duplicate_detection

    original = tmp_path / "video.mkv"
    downloaded = tmp_path / "video (1).mkv"
    original.write_bytes(b"original")
    downloaded.write_bytes(b"replacement")
    signature = capture_replace_signature(original)
    assert signature is not None
    copyfileobj = duplicate_detection.shutil.copyfileobj

    def mutate_during_copy(source, destination):
        copyfileobj(source, destination)
        original.write_bytes(b"changed during staging")

    monkeypatch.setattr(duplicate_detection.shutil, "copyfileobj", mutate_during_copy)
    with pytest.raises(OSError, match="changed while preparing"):
        replace_completed_download(downloaded, original, signature)
    assert original.read_bytes() == b"changed during staging"
    assert downloaded.read_bytes() == b"replacement"
    assert not list(tmp_path.glob("*.replace"))


def test_preserves_original_and_download_if_atomic_replace_fails(tmp_path: Path, monkeypatch) -> None:
    from mediagrab import duplicate_detection

    original = tmp_path / "video.mkv"
    downloaded = tmp_path / "video (1).mkv"
    original.write_bytes(b"original")
    downloaded.write_bytes(b"replacement")
    signature = capture_replace_signature(original)
    assert signature is not None

    def fail_replace(_source, _target):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(duplicate_detection.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replacement failure"):
        replace_completed_download(downloaded, original, signature)
    assert original.read_bytes() == b"original"
    assert downloaded.read_bytes() == b"replacement"
    assert not list(tmp_path.glob("*.replace"))



def test_optional_checksum_confirms_or_rules_out_same_size_candidate(tmp_path: Path) -> None:
    target = tmp_path / "video.mkv"
    contents = b"saved media"
    target.write_bytes(contents)
    entry = {
        "filename": "video.mkv",
        "destination": str(tmp_path),
        "size": len(contents),
        "outcome": "Completed",
    }
    matching = "sha256:" + hashlib.sha256(contents).hexdigest()
    different_same_size = "sha256:" + hashlib.sha256(b"other media").hexdigest()

    assert find_completed_file_duplicates(
        "video.mkv", [entry], expected_checksum=matching
    ) == [entry]
    assert find_completed_file_duplicates(
        "video.mkv", [entry], expected_checksum=different_same_size
    ) == []
