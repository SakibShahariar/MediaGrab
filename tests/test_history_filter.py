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
        "category": "Direct download",
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



def test_last_used_filter_preferences_round_trip_and_validation(tmp_path):
    from mediagrab.history_filter import (
        load_history_filter_preferences,
        save_history_filter_preferences,
    )

    path = tmp_path / "history-filters.json"
    selected = {
        "query": "Example video",
        "status": "Completed",
        "file_type": "Video",
        "domain": "example.com",
        "date_range": "Last 7 days",
        "size_filter": "Under 100 MB",
        "category": "HLS/DASH stream",
    }
    save_history_filter_preferences(selected, path)
    assert load_history_filter_preferences(path) == selected


def test_invalid_or_corrupt_filter_preferences_fall_back_safely(tmp_path):
    import json

    from mediagrab.history_filter import (
        load_history_filter_preferences,
        save_history_filter_preferences,
    )

    path = tmp_path / "history-filters.json"
    path.write_text(json.dumps({
        "status": "Unknown",
        "file_type": "Video",
        "query": "x" * 300,
        "domain": 42,
    }), encoding="utf-8")
    restored = load_history_filter_preferences(path)
    assert restored["status"] == "All statuses"
    assert restored["file_type"] == "Video"
    assert len(restored["query"]) == 256
    assert restored["domain"] == ""
    path.write_text("{broken", encoding="utf-8")
    assert load_history_filter_preferences(path)["file_type"] == "All files"
    with pytest.raises(ValueError, match="status"):
        save_history_filter_preferences({"status": "Unknown"}, path)


def test_category_filter_and_legacy_default(entry):
    assert matches_history_entry(entry, category="Direct download")
    assert not matches_history_entry(entry, category="HLS/DASH stream")
    entry.pop("category")
    assert matches_history_entry(entry, category="Uncategorized")


def test_history_filter_handles_large_histories():
    history = [{"source_url": f"https://cdn{i % 10}.example.test/{i}.mp4", "filename": f"{i}.mp4", "destination": "/downloads", "size": i * 1024, "outcome": "Completed" if i % 2 else "Failed", "timestamp": "2026-11-02T00:00:00+00:00", "category": "Direct download" if i % 3 else "HLS/DASH stream"} for i in range(1000)]
    selected = [item for item in history if matches_history_entry(item, query="cdn1", status="Completed", file_type="Video", domain="example.test", category="Direct download")]
    assert selected and len(selected) < len(history)
    assert all(item["outcome"] == "Completed" and item["category"] == "Direct download" and "cdn1" in item["source_url"] for item in selected)
