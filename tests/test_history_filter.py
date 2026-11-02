"""Tests for composable download-history filters."""

from datetime import datetime, timezone

import pytest

from mediagrab.history_filter import matches_history_entry


@pytest.fixture
def entry():
    return {
        "source_url": "https://cdn.example.test/media/video.mp4?token=redacted",
        "filename": "video.mp4",
        "destination": "/home/user/Downloads",
        "size": 250 * 1024 * 1024,
        "outcome": "Completed",
        "timestamp": "2026-11-02T00:00:00+00:00",
        "checksum_status": "passed",
    }


def test_history_filters_can_be_combined(entry):
    assert matches_history_entry(
        entry, query="video", status="Completed", file_type="Video",
        domain="example.test",
        since=datetime(2026, 11, 1, tzinfo=timezone.utc),
        size_filter="100 MB–1 GB",
    )
    assert not matches_history_entry(entry, status="Failed")
    assert not matches_history_entry(entry, file_type="Audio")
    assert not matches_history_entry(entry, domain="not-example.test")
    assert not matches_history_entry(entry, size_filter="Under 100 MB")


@pytest.mark.parametrize(
    ("filename", "file_type"),
    [
        ("master.m3u8", "HLS/DASH"), ("manifest.mpd", "HLS/DASH"),
        ("captions.vtt", "Subtitles"), ("song.flac", "Audio"),
        ("archive.zip", "Other"),
    ],
)
def test_history_file_type_filters(entry, filename, file_type):
    entry["filename"] = filename
    assert matches_history_entry(entry, file_type=file_type)


def test_domain_filter_matches_exact_host_and_subdomains(entry):
    assert matches_history_entry(entry, domain="cdn.example.test")
    assert matches_history_entry(entry, domain="example.test")
    assert not matches_history_entry(entry, domain="ample.test")


def test_date_filter_rejects_old_or_invalid_timestamps(entry):
    cutoff = datetime(2026, 11, 2, 0, 0, 1, tzinfo=timezone.utc)
    assert not matches_history_entry(entry, since=cutoff)
    entry["timestamp"] = "not-a-date"
    assert not matches_history_entry(entry, since=cutoff)


def test_size_filters_handle_unknown_and_boundaries(entry):
    entry["size"] = None
    assert matches_history_entry(entry, size_filter="Unknown size")
    assert not matches_history_entry(entry, size_filter="Under 100 MB")
    entry["size"] = 100 * 1024 * 1024
    assert matches_history_entry(entry, size_filter="100 MB–1 GB")
    entry["size"] = 1024 * 1024 * 1024 + 1
    assert matches_history_entry(entry, size_filter="Over 1 GB")


def test_search_is_case_insensitive_and_matches_url_or_destination(entry):
    assert matches_history_entry(entry, query="CDN.EXAMPLE")
    assert matches_history_entry(entry, query="/downloads")
    assert not matches_history_entry(entry, query="missing")
