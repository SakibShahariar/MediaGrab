"""FFmpeg-backed HLS/DASH download task.

FFmpeg is an optional system dependency. This adapter remuxes the selected stream
without re-encoding; it does not bypass DRM or site access controls.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from mediagrab.downloader import DownloadError, DownloadProgress, filename_from_url

ProgressCallback = Callable[[DownloadProgress], None]


class MediaStreamTask:
    """Download an HLS or DASH stream with FFmpeg, with cancellation and safe finalize."""

    def __init__(
        self,
        url: str,
        destination: str | Path,
        *,
        ffmpeg_path: str | None = None,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only valid HTTP(S) stream URLs are supported")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs with embedded credentials are not accepted")
        self.url = url
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
        target = self.destination / f"{stem}.mkv"
        temporary = self.destination / f".{stem}.mediagrab-part.mkv"
        if target.exists():
            self._set_state("failed")
            raise DownloadError(f"Destination already exists: {target}")
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError as exc:
                self._set_state("failed")
                raise DownloadError(f"Could not clear previous incomplete stream output: {exc}") from exc

        command = [
            self.ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error",
            "-stats_period", "0.5", "-progress", "pipe:1", "-i", self.url,
            "-map", "0", "-c", "copy", "-f", "matroska", "-n", str(temporary),
        ]
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
