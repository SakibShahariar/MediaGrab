""""Tests for FFmpeg-backed stream downloading without requiring FFmpeg."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from mediagrab.downloader import DownloadError
from mediagrab.media_stream import MediaStreamTask


class FakeProcess:
    def __init__(self, lines: str, returncode: int):
        self.stdout = io.StringIO(lines)
        self.returncode = returncode
        self.terminated = False

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def test_requires_ffmpeg_and_rejects_embedded_credentials(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("mediagrab.media_stream.shutil.which", lambda _name: None)
    with pytest.raises(ValueError, match="FFmpeg is required"):
        MediaStreamTask("https://cdn.example/master.m3u8", tmp_path)
    with pytest.raises(ValueError, match="embedded credentials"):
        MediaStreamTask(
            "https://user:secret@cdn.example/master.m3u8",
            tmp_path,
            ffmpeg_path="/usr/bin/ffmpeg",
        )


def test_successful_stream_is_finalized_as_mkv_and_reports_progress(
    tmp_path: Path, monkeypatch
) -> None:
    url = "https://cdn.example/master.m3u8?token=secret"
    task = MediaStreamTask(url, tmp_path, ffmpeg_path="/fake/ffmpeg")
    captured = {}

    def popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(command[-1]).write_bytes(b"fake-matroska")
        return FakeProcess(
            "total_size=5\nprogress=continue\ntotal_size=13\nprogress=end\n", 0
        )

    monkeypatch.setattr("mediagrab.media_stream.subprocess.Popen", popen)
    updates = []
    target = task.run(updates.append)

    assert target.name == "master.mkv"
    assert target.read_bytes() == b"fake-matroska"
    assert task.state == "completed"
    assert updates[0].received == 5
    assert updates[0].total is None
    assert updates[-1].state == "completed"
    assert updates[-1].received == len(b"fake-matroska")
    command = captured["command"]
    assert command[0] == "/fake/ffmpeg"
    assert command[command.index("-i") + 1] == url
    assert command[command.index("-c") + 1] == "copy"
    assert command[command.index("-f") + 1] == "matroska"
    assert command[-1].endswith(".mediagrab-part.mkv")
    assert captured["kwargs"]["stdin"] is not None
    assert captured["kwargs"]["stdout"] is not None
    assert captured["kwargs"]["stderr"] is not None


def test_ffmpeg_failure_does_not_expose_url_or_leave_partial_output(
    tmp_path: Path, monkeypatch
) -> None:
    task = MediaStreamTask(
        "https://cdn.example/master.m3u8?token=secret",
        tmp_path,
        ffmpeg_path="/fake/ffmpeg",
    )
    monkeypatch.setattr(
        "mediagrab.media_stream.subprocess.Popen",
        lambda *_a, **_k: FakeProcess("", 1),
    )
    with pytest.raises(DownloadError, match="FFmpeg could not download") as error:
        task.run()
    assert "secret" not in str(error.value)
    assert task.state == "failed"
    assert not (tmp_path / ".master.mediagrab-part.mkv").exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "master.mkv").write_bytes(b"keep")
    task = MediaStreamTask(
        "https://cdn.example/master.m3u8", tmp_path, ffmpeg_path="/fake/ffmpeg"
    )
    with pytest.raises(DownloadError, match="already exists"):
        task.run()
    assert (tmp_path / "master.mkv").read_bytes() == b"keep"


def test_cancel_before_start(tmp_path: Path) -> None:
    task = MediaStreamTask(
        "https://cdn.example/master.m3u8", tmp_path, ffmpeg_path="/fake/ffmpeg"
    )
    task.cancel()
    with pytest.raises(DownloadError, match="cancelled before start"):
        task.run()
    assert task.state == "cancelled"
