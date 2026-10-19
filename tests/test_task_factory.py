"""Tests for routing queued URLs to the appropriate download engine."""

from pathlib import Path

import pytest

from mediagrab import task_factory
from mediagrab.capture import MediaKind


def test_hls_and_dash_urls_use_stream_task(tmp_path: Path, monkeypatch) -> None:
    created = []

    class FakeStreamTask:
        def __init__(self, url, destination):
            created.append((url, destination))

    monkeypatch.setattr(task_factory, "MediaStreamTask", FakeStreamTask)
    monkeypatch.setattr(
        task_factory, "classify_media",
        lambda url: MediaKind.HLS if url.endswith(".m3u8") else MediaKind.DASH,
    )

    hls = task_factory.create_download_task("https://cdn.test/live.m3u8", tmp_path)
    dash = task_factory.create_download_task("https://cdn.test/manifest.mpd", tmp_path)

    assert isinstance(hls, FakeStreamTask)
    assert isinstance(dash, FakeStreamTask)
    assert created == [
        ("https://cdn.test/live.m3u8", tmp_path),
        ("https://cdn.test/manifest.mpd", tmp_path),
    ]


def test_direct_and_unknown_urls_use_http_task(tmp_path: Path, monkeypatch) -> None:
    class FakeDownloadTask:
        def __init__(self, url, destination):
            self.url = url
            self.destination = destination

    monkeypatch.setattr(task_factory, "DownloadTask", FakeDownloadTask)
    monkeypatch.setattr(task_factory, "classify_media", lambda _url: MediaKind.UNKNOWN)

    task = task_factory.create_download_task("https://cdn.test/file", tmp_path)

    assert isinstance(task, FakeDownloadTask)
    assert task.url == "https://cdn.test/file"
    assert task.destination == tmp_path


def test_missing_ffmpeg_error_is_preserved_for_ui(tmp_path: Path, monkeypatch) -> None:
    def missing_ffmpeg(_url, _destination):
        raise ValueError("FFmpeg is required for HLS/DASH downloads")

    monkeypatch.setattr(task_factory, "classify_media", lambda _url: MediaKind.HLS)
    monkeypatch.setattr(task_factory, "MediaStreamTask", missing_ffmpeg)

    with pytest.raises(ValueError, match="FFmpeg is required"):
        task_factory.create_download_task("https://cdn.test/live.m3u8", tmp_path)
