"""Small, independently testable HTTP(S) download core.

This module deliberately has no GTK dependency. UI code can run each DownloadTask
in a worker thread and marshal progress callbacks back to the main loop.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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

    Cancellation is cooperative. Interrupted transfers retain a .part file.
    Calling run() again on a new task resumes when the server supports byte ranges;
    if the server ignores Range, the partial is safely restarted from byte zero.
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
        metadata = partial.with_name(f"{partial.name}.json")

        if target.exists():
            self._set_state("failed")
            raise DownloadError(f"Destination already exists: {target}")
        offset = partial.stat().st_size if partial.exists() else 0
        validator: tuple[str, str] | None = None
        if offset and metadata.exists():
            try:
                saved = json.loads(metadata.read_text(encoding="utf-8"))
                if saved.get("url_sha256") == hashlib.sha256(self.url.encode()).hexdigest():
                    if saved.get("etag"):
                        validator = ("If-Range", saved["etag"])
                    elif saved.get("last_modified"):
                        validator = ("If-Range", saved["last_modified"])
                else:
                    # A same-named URL may point to a different resource.
                    offset = 0
            except (OSError, ValueError, TypeError):
                # Unreadable metadata cannot safely validate the partial.
                offset = 0
        # Never append bytes from an unvalidated partial. Older partials without
        # sidecar metadata are restarted from byte zero.
        if offset and validator is None:
            offset = 0

        if self._cancel.is_set():
            self._set_state("cancelled")
            raise DownloadError("Download cancelled before start")

        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            if validator is not None:
                headers[validator[0]] = validator[1]
        request = urllib.request.Request(self.url, headers=headers)
        started = time.monotonic()
        received = 0
        total: int | None = None
        self._set_state("downloading")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise DownloadError(f"Unexpected HTTP status: {status}")

                append = offset > 0 and status == 206
                if offset and status == 200:
                    # Server ignored Range: restart rather than appending duplicate bytes.
                    offset = 0
                elif offset and status != 206:
                    raise DownloadError(f"Server cannot resume this download (HTTP {status})")

                content_range = response.headers.get("Content-Range", "")
                range_match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                if append:
                    if range_match is None:
                        raise DownloadError("Server returned an invalid Content-Range for resume")
                    range_start, range_end, range_total = map(int, range_match.groups())
                    if (
                        range_start != offset
                        or range_end < range_start
                        or range_total <= range_end
                        or range_end != range_total - 1
                    ):
                        raise DownloadError("Server returned an inconsistent Content-Range for resume")

                etag = response.headers.get("ETag")
                last_modified = response.headers.get("Last-Modified")
                if etag or last_modified:
                    metadata_tmp = metadata.with_name(f"{metadata.name}.tmp")
                    try:
                        metadata_tmp.write_text(
                            json.dumps({
                                "url_sha256": hashlib.sha256(self.url.encode()).hexdigest(),
                                "etag": etag,
                                "last_modified": last_modified,
                            }),
                            encoding="utf-8",
                        )
                        os.replace(metadata_tmp, metadata)
                    except OSError:
                        try:
                            metadata_tmp.unlink(missing_ok=True)
                        except OSError:
                            pass
                        # A failed metadata write must not fail an otherwise valid transfer.
                content_length = response.headers.get("Content-Length")
                response_length: int | None = None
                if content_length:
                    try:
                        response_length = int(content_length)
                    except ValueError:
                        response_length = None
                    if response_length is not None and response_length < 0:
                        response_length = None
                if append:
                    total = range_total
                    if response_length is not None and response_length != range_end - range_start + 1:
                        raise DownloadError("Content-Length does not match Content-Range")
                else:
                    total = response_length

                mode = "ab" if append else "wb"
                received = offset if append else 0
                with partial.open(mode) as output:
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
            try:
                metadata.unlink(missing_ok=True)
            except OSError:
                pass  # A stale sidecar must not turn a completed download into a failure.
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
            if exc.code == 416 and offset > 0 and partial.exists():
                # A server may reject Range when the partial is already complete.
                # Promote it only when the server reports a total matching its size.
                match = re.fullmatch(
                    r"bytes \*/(\d+)", exc.headers.get("Content-Range", "")
                )
                if match is not None and partial.stat().st_size == int(match.group(1)):
                    try:
                        exc.close()
                        if self._cancel.is_set():
                            self._set_state("cancelled")
                            raise DownloadError("Download cancelled")
                        os.replace(partial, target)
                        try:
                            metadata.unlink(missing_ok=True)
                        except OSError:
                            pass
                        self._set_state("completed")
                        if on_progress is not None:
                            size = target.stat().st_size
                            elapsed = max(time.monotonic() - started, 0.001)
                            on_progress(
                                DownloadProgress(
                                    received=size,
                                    total=size,
                                    bytes_per_second=size / elapsed,
                                    state="completed",
                                )
                            )
                        return target
                    except OSError as file_error:
                        self._set_state("failed")
                        raise DownloadError(
                            f"Could not finalize completed partial download: {file_error}"
                        ) from file_error
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
