"""Tests for pending duplicate URL detection."""
from mediagrab.duplicate_detection import has_pending_duplicate


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
