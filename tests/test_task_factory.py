"""Tests for routing queued URLs to the appropriate download engine."""

from pathlib import Path

import pytest

from mediagrab import task_factory
from mediagrab.capture import MediaKind


def test_hls_and_dash_urls_use_stream_task(tmp_path: Path, monkeypatch) -> None:
    created = []

    class FakeStreamTask:
        def __init__(self, url, destination, **kwargs):
            created.append((url, destination, kwargs.get("output_format", "mkv")))

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
        ("https://cdn.test/live.m3u8", tmp_path, "mkv"),
        ("https://cdn.test/manifest.mpd", tmp_path, "mkv"),
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
    def missing_ffmpeg(_url, _destination, **_kwargs):
        raise ValueError("FFmpeg is required for HLS/DASH downloads")

    monkeypatch.setattr(task_factory, "classify_media", lambda _url: MediaKind.HLS)
    monkeypatch.setattr(task_factory, "MediaStreamTask", missing_ffmpeg)

    with pytest.raises(ValueError, match="FFmpeg is required"):
        task_factory.create_download_task("https://cdn.test/live.m3u8", tmp_path)



def test_embedded_credentials_are_rejected_for_every_task_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="embedded credentials"):
        task_factory.create_download_task("https://user:secret@cdn.test/file.zip", tmp_path)


def test_expected_checksum_is_forwarded_to_both_task_engines(tmp_path: Path, monkeypatch) -> None:
    created = []

    class FakeTask:
        def __init__(self, url, destination, **kwargs):
            created.append((url, destination, kwargs.get("expected_checksum")))

    monkeypatch.setattr(task_factory, "DownloadTask", FakeTask)
    monkeypatch.setattr(task_factory, "MediaStreamTask", FakeTask)
    monkeypatch.setattr(
        task_factory, "classify_media",
        lambda url: MediaKind.HLS if url.endswith(".m3u8") else MediaKind.UNKNOWN,
    )
    checksum = "sha256:" + "a" * 64

    task_factory.create_download_task("https://cdn.test/file.bin", tmp_path, expected_checksum=checksum)
    task_factory.create_download_task("https://cdn.test/live.m3u8", tmp_path, expected_checksum=checksum)

    assert created == [
        ("https://cdn.test/file.bin", tmp_path, checksum),
        ("https://cdn.test/live.m3u8", tmp_path, checksum),
    ]


def test_output_format_is_forwarded_to_stream_task(tmp_path: Path, monkeypatch) -> None:
    created = []

    class FakeStreamTask:
        def __init__(self, url, destination, **kwargs):
            created.append(kwargs.get("output_format"))

    monkeypatch.setattr(task_factory, "MediaStreamTask", FakeStreamTask)
    monkeypatch.setattr(task_factory, "classify_media", lambda _url: MediaKind.HLS)

    task_factory.create_download_task(
        "https://cdn.test/live.m3u8", tmp_path, output_format="mp4"
    )

    assert created == ["mp4"]


def test_dash_video_stream_index_is_forwarded_with_and_without_checksum(tmp_path: Path, monkeypatch) -> None:
    created = []

    class FakeStreamTask:
        def __init__(self, url, destination, **kwargs):
            created.append(kwargs.get("dash_video_stream_index"))

    monkeypatch.setattr(task_factory, "MediaStreamTask", FakeStreamTask)
    monkeypatch.setattr(task_factory, "classify_media", lambda _url: MediaKind.DASH)

    task_factory.create_download_task(
        "https://cdn.test/manifest.mpd", tmp_path, dash_video_stream_index=1
    )
    task_factory.create_download_task(
        "https://cdn.test/manifest.mpd", tmp_path,
        expected_checksum="sha256:" + "a" * 64,
        dash_video_stream_index=2,
    )

    assert created == [1, 2]
