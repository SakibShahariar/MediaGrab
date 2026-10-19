"""Small, independently testable HTTP(S) download core.

This module deliberately has no GTK dependency. UI code can run each DownloadTask
in a worker thread and marshal progress callbacks back to the main loop.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class DownloadProgress:
    received: int
    total: int | None
    bytes_per_second: float
    state: str


ProgressCallback = Callable[[DownloadProgress], None]


class DownloadError(Exception):
    """Raised when a download cannot be completed."""


def filename_from_url(url: str) -> str:
    """Choose a conservative filename from a URL, with a safe fallback."""
    parsed = urlparse(url)
    candidate = unquote(Path(parsed.path).name).strip()
    if candidate in {"", ".", ".."}:
        candidate = parsed.netloc or "download"
    candidate = "".join(
        "_" if char in "/\\\0" or ord(char) < 32 else char
        for char in candidate
    ).strip(" .")
    return candidate or "download"


class DownloadTask:
    """Download one HTTP(S) resource to a destination directory.

    Cancellation is cooperative. A partial file is retained as a .part file.
    This version intentionally starts fresh rather than resuming automatically.
    """

    def __init__(
        self,
        url: str,
        destination: str | Path,
        *,
        timeout: float = 30.0,
        chunk_size: int = 128 * 1024,
        user_agent: str = "MediaGrab/0.1",
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only valid HTTP(S) URLs are supported")
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")

        self.url = url
        self.destination = Path(destination)
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.user_agent = user_agent
        self._cancel = threading.Event()
        self._state_lock = threading.Lock()
        self._state = "queued"

    @property
    def state(self) -> str:
        with self._state_lock:
            return self._state

    def cancel(self) -> None:
        self._cancel.set()

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            self._state = state

    def run(self, on_progress: ProgressCallback | None = None) -> Path:
        """Perform the transfer. Call from a worker thread, not the GTK thread."""
        if self.state != "queued":
            raise DownloadError(f"Task cannot start from state {self.state!r}")

        if self._cancel.is_set():
            self._set_state("cancelled")
            raise DownloadError("Download cancelled before start")

        self.destination.mkdir(parents=True, exist_ok=True)
        filename = filename_from_url(self.url)
        target = self.destination / filename
        partial = self.destination / f"{filename}.part"

        if target.exists():
            self._set_state("failed")
            raise DownloadError(f"Destination already exists: {target}")
        if partial.exists():
            self._set_state("failed")
            raise DownloadError(
                f"Partial file already exists: {partial}; move or remove it before retrying"
            )

        if self._cancel.is_set():
            self._set_state("cancelled")
            raise DownloadError("Download cancelled before start")

        request = urllib.request.Request(
            self.url,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
        )
        started = time.monotonic()
        received = 0
        total: int | None = None
        self._set_state("downloading")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise DownloadError(f"Unexpected HTTP status: {status}")

                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        total = int(content_length)
                    except ValueError:
                        total = None
                    if total is not None and total < 0:
                        total = None

                with partial.open("xb") as output:
                    while True:
                        if self._cancel.is_set():
                            self._set_state("cancelled")
                            raise DownloadError("Download cancelled")

                        chunk = response.read(self.chunk_size)
                        if not chunk:
                            break
                        output.write(chunk)
                        received += len(chunk)

                        elapsed = max(time.monotonic() - started, 0.001)
                        if on_progress is not None:
                            on_progress(
                                DownloadProgress(
                                    received=received,
                                    total=total,
                                    bytes_per_second=received / elapsed,
                                    state="downloading",
                                )
                            )

                    output.flush()
                    os.fsync(output.fileno())

            if self._cancel.is_set():
                self._set_state("cancelled")
                raise DownloadError("Download cancelled")

            if total is not None and received != total:
                raise DownloadError(
                    f"Incomplete response: expected {total} bytes, received {received}"
                )

            os.replace(partial, target)
            self._set_state("completed")
            if on_progress is not None:
                elapsed = max(time.monotonic() - started, 0.001)
                on_progress(
                    DownloadProgress(
                        received=received,
                        total=total if total is not None else received,
                        bytes_per_second=received / elapsed,
                        state="completed",
                    )
                )
            return target

        except urllib.error.HTTPError as exc:
            self._set_state("failed")
            raise DownloadError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            self._set_state("failed")
            raise DownloadError(f"Network error: {exc.reason}") from exc
        except DownloadError:
            if self.state != "cancelled":
                self._set_state("failed")
            raise
        except OSError as exc:
            self._set_state("failed")
            raise DownloadError(f"File or network I/O error: {exc}") from exc
