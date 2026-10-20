"""FFmpeg-backed HLS/DASH download task with optional external tracks."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from mediagrab.downloader import DownloadError, DownloadProgress, filename_from_url, unique_output_path

ProgressCallback = Callable[[DownloadProgress], None]


def _validate_http_url(url: str, label: str = "URL") -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} must be a valid HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label}s with embedded credentials are not accepted")


def build_ffmpeg_command(
    ffmpeg_path: str,
    video_url: str,
    temporary_output: str | Path,
    *,
    audio_url: str | None = None,
    subtitle_url: str | None = None,
) -> list[str]:
    """Build a stream-copy command; optional tracks are explicit separate inputs."""
    _validate_http_url(video_url, "Video URL")
    if audio_url:
        _validate_http_url(audio_url, "Audio URL")
    if subtitle_url:
        _validate_http_url(subtitle_url, "Subtitle URL")

    command = [
        ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-stats_period", "0.5", "-progress", "pipe:1",
        "-i", video_url,
    ]
    next_input = 1
    audio_index: int | None = None
    subtitle_index: int | None = None
    if audio_url:
        audio_index = next_input
        command.extend(["-i", audio_url])
        next_input += 1
    if subtitle_url:
        subtitle_index = next_input
        command.extend(["-i", subtitle_url])

    # Explicit selections replace that media type from the video input. Mapping
    # all of input 0 as well would silently include duplicate/default audio or
    # subtitle streams alongside the user's selected track.
    if audio_index is None and subtitle_index is None:
        command.extend(["-map", "0"])
    else:
        command.extend(["-map", "0:v?"])
        if audio_index is None:
            command.extend(["-map", "0:a?"])
        else:
            command.extend(["-map", f"{audio_index}:a:0?"])
        if subtitle_index is None:
            command.extend(["-map", "0:s?"])
        else:
            command.extend(["-map", f"{subtitle_index}:s:0?"])

    command.extend(["-c", "copy", "-f", "matroska", "-n", str(temporary_output)])
    return command


class MediaStreamTask:
    """Download a stream with FFmpeg, optional selected tracks, cancellation and safe finalize."""

    def __init__(
        self,
        url: str,
        destination: str | Path,
        *,
        audio_url: str | None = None,
        subtitle_url: str | None = None,
        ffmpeg_path: str | None = None,
    ) -> None:
        _validate_http_url(url)
        if audio_url:
            _validate_http_url(audio_url, "Audio URL")
        if subtitle_url:
            _validate_http_url(subtitle_url, "Subtitle URL")
        self.url = url
        self.audio_url = audio_url or None
        self.subtitle_url = subtitle_url or None
        self.destination = Path(destination)
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._state = "queued"
        if not self.ffmpeg_path:
            raise ValueError("FFmpeg is required for HLS/DASH downloads; install it with: sudo dnf install ffmpeg")

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _set_state(self, value: str) -> None:
        with self._lock:
            self._state = value

    def cancel(self) -> None:
        self._cancel.set()

    def run(self, on_progress: ProgressCallback | None = None) -> Path:
        if self.state != "queued":
            raise DownloadError(f"Task cannot start from state {self.state!r}")
        if self._cancel.is_set():
            self._set_state("cancelled")
            raise DownloadError("Download cancelled before start")

        self.destination.mkdir(parents=True, exist_ok=True)
        original = filename_from_url(self.url)
        stem = Path(original).stem or "media"
        target = unique_output_path(self.destination, f"{stem}.mkv")
        temporary = self.destination / f".{target.stem}.mediagrab-part.mkv"
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError as exc:
                self._set_state("failed")
                raise DownloadError(f"Could not clear previous incomplete stream output: {exc}") from exc

        command = build_ffmpeg_command(
            self.ffmpeg_path, self.url, temporary,
            audio_url=self.audio_url, subtitle_url=self.subtitle_url,
        )
        self._set_state("downloading")
        started = time.monotonic()
        last_bytes = 0
        last_time = started
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                if self._cancel.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    self._set_state("cancelled")
                    raise DownloadError("Stream download cancelled")
                key, separator, value = line.strip().partition("=")
                if separator and key == "total_size" and value.isdigit() and on_progress:
                    current = int(value)
                    now = time.monotonic()
                    speed = max(0, current - last_bytes) / max(now - last_time, 0.001)
                    on_progress(DownloadProgress(current, None, speed, "downloading"))
                    last_bytes, last_time = current, now
            return_code = process.wait()
            if self._cancel.is_set():
                self._set_state("cancelled")
                raise DownloadError("Stream download cancelled")
            if return_code != 0:
                self._set_state("failed")
                raise DownloadError(
                    f"FFmpeg could not download this stream (exit code {return_code}). "
                    "The URL may have expired, the stream may require browser authentication, "
                    "or the format may be unsupported."
                )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                self._set_state("failed")
                raise DownloadError("FFmpeg finished without producing a media file")
            if target.exists():
                self._set_state("failed")
                raise DownloadError(f"Destination already exists: {target}")
            os.replace(temporary, target)
            self._set_state("completed")
            if on_progress:
                size = target.stat().st_size
                elapsed = max(time.monotonic() - started, 0.001)
                on_progress(DownloadProgress(size, size, size / elapsed, "completed"))
            return target
        except FileNotFoundError as exc:
            self._set_state("failed")
            raise DownloadError("FFmpeg executable was not found; install FFmpeg and retry") from exc
        except OSError as exc:
            self._set_state("failed")
            raise DownloadError(f"Could not run FFmpeg: {exc}") from exc
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            if self.state != "completed":
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
