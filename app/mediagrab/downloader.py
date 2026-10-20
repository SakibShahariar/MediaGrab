"""Small, independently testable HTTP(S) download core.

This module deliberately has no GTK dependency. UI code can run each DownloadTask
in a worker thread and marshal progress callbacks back to the main loop.
"""

from __future__ import annotations

import hashlib
import http.client
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


class DownloadPaused(DownloadError):
    """Raised when a direct download is paused without discarding its partial data."""


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



def unique_output_path(directory: Path, filename: str) -> Path:
    """Choose a non-existing output name while preserving resumable base partials."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    extension = candidate.suffix
    index = 1
    candidate = directory / f"{stem} ({index}){extension}"
    while candidate.exists() or candidate.with_name(candidate.name + ".part").exists():
        index += 1
        candidate = directory / f"{stem} ({index}){extension}"
    return candidate


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
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
        except ValueError as exc:
            raise ValueError("Only valid HTTP(S) URLs are supported") from exc
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise ValueError("Only valid HTTP(S) URLs are supported")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs with embedded credentials are not accepted")
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.url = url
        self.destination = Path(destination)
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.user_agent = user_agent
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._state_lock = threading.Lock()
        self._state = "queued"

    @property
    def state(self) -> str:
        with self._state_lock:
            return self._state

    def cancel(self) -> None:
        self._cancel.set()

    def pause(self) -> None:
        """Request a cooperative pause; the validated partial is kept for resume."""
        self._pause.set()

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
        if self._pause.is_set():
            self._set_state("paused")
            raise DownloadPaused("Download paused before start")

        self.destination.mkdir(parents=True, exist_ok=True)
        filename = filename_from_url(self.url)
        target = unique_output_path(self.destination, filename)
        partial = self.destination / f"{target.name}.part"
        metadata = partial.with_name(f"{partial.name}.json")

        offset = partial.stat().st_size if partial.exists() else 0
        validator: tuple[str, str] | None = None
        if offset and metadata.exists():
            try:
                saved = json.loads(metadata.read_text(encoding="utf-8"))
                if saved.get("url_sha256") == hashlib.sha256(self.url.encode()).hexdigest():
                    etag = saved.get("etag")
                    modified = saved.get("last_modified")
                    if etag and not etag.startswith("W/"):
                        validator = ("If-Range", etag)
                    elif modified:
                        validator = ("If-Range", modified)
                else:
                    offset = 0
            except (OSError, ValueError, TypeError):
                offset = 0
        # Never append bytes from an unvalidated partial.
        if offset and validator is None:
            offset = 0

        if self._cancel.is_set():
            self._set_state("cancelled")
            raise DownloadError("Download cancelled before start")

        started = time.monotonic()
        received = offset
        total: int | None = None
        self._set_state("downloading")

        try:
            while True:
                headers = {"User-Agent": self.user_agent, "Accept-Encoding": "identity"}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                    if validator is not None:
                        headers[validator[0]] = validator[1]
                request = urllib.request.Request(self.url, headers=headers)

                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    if status < 200 or status >= 300:
                        raise DownloadError(f"Unexpected HTTP status: {status}")

                    append = offset > 0 and status == 206
                    if status == 206 and offset == 0:
                        raise DownloadError(
                            "Server returned HTTP 206 without a requested byte range"
                        )
                    if offset and status == 200:
                        # If-Range failed or Range was ignored: discard old bytes.
                        offset = 0
                        received = 0
                    elif offset and status != 206:
                        raise DownloadError(
                            f"Server cannot resume this download (HTTP {status})"
                        )

                    range_end: int | None = None
                    if append:
                        content_range = response.headers.get("Content-Range", "")
                        range_match = re.fullmatch(
                            r"bytes (\d+)-(\d+)/(\d+)", content_range
                        )
                        if range_match is None:
                            raise DownloadError(
                                "Server returned an invalid Content-Range for resume"
                            )
                        range_start, range_end, range_total = map(
                            int, range_match.groups()
                        )
                        if (
                            range_start != offset
                            or range_end < range_start
                            or range_total <= range_end
                            or (total is not None and range_total != total)
                        ):
                            raise DownloadError(
                                "Server returned an inconsistent Content-Range for resume"
                            )
                        total = range_total

                    etag = response.headers.get("ETag")
                    last_modified = response.headers.get("Last-Modified")
                    if etag or last_modified:
                        metadata_tmp = metadata.with_name(f"{metadata.name}.tmp")
                        try:
                            metadata_tmp.write_text(
                                json.dumps({
                                    "url_sha256": hashlib.sha256(
                                        self.url.encode()
                                    ).hexdigest(),
                                    "etag": etag,
                                    "last_modified": last_modified,
                                }),
                                encoding="utf-8",
                            )
                            os.replace(metadata_tmp, metadata)
                            if etag and not etag.startswith("W/"):
                                validator = ("If-Range", etag)
                            elif last_modified:
                                validator = ("If-Range", last_modified)
                        except OSError:
                            try:
                                metadata_tmp.unlink(missing_ok=True)
                            except OSError:
                                pass
                            # Metadata failure must not fail an otherwise valid transfer.

                    content_length = response.headers.get("Content-Length")
                    response_length: int | None = None
                    if content_length is not None:
                        if re.fullmatch(r"\d+", content_length) is None:
                            raise DownloadError("Server returned an invalid Content-Length")
                        response_length = int(content_length)

                    if append:
                        segment_length = range_end - range_start + 1
                        if (
                            response_length is not None
                            and response_length != segment_length
                        ):
                            raise DownloadError(
                                "Content-Length does not match Content-Range"
                            )
                    else:
                        total = response_length

                    mode = "ab" if append else "wb"
                    received = offset if append else 0
                    segment_received = 0
                    with partial.open(mode) as output:
                        while True:
                            if self._cancel.is_set():
                                self._set_state("cancelled")
                                raise DownloadError("Download cancelled")
                            if self._pause.is_set():
                                self._set_state("paused")
                                raise DownloadPaused("Download paused")
                            chunk = response.read(self.chunk_size)
                            if not chunk:
                                break
                            output.write(chunk)
                            received += len(chunk)
                            segment_received += len(chunk)
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

                    if append and segment_received != range_end - range_start + 1:
                        raise DownloadError(
                            "Incomplete range response: expected "
                            f"{range_end - range_start + 1} bytes, received {segment_received}"
                        )
                    if not append and total is not None and received != total:
                        raise DownloadError(
                            f"Incomplete response: expected {total} bytes, received {received}"
                        )

                if self._cancel.is_set():
                    self._set_state("cancelled")
                    raise DownloadError("Download cancelled")

                # A valid 206 may contain only a bounded segment. Keep requesting
                # from the next byte until the server-reported representation ends.
                if append and total is not None and range_end is not None:
                    if range_end < total - 1:
                        offset = received
                        continue
                    if received != total:
                        raise DownloadError(
                            f"Incomplete response: expected {total} bytes, received {received}"
                        )
                break

            os.replace(partial, target)
            try:
                metadata.unlink(missing_ok=True)
            except OSError:
                pass
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
                match = re.fullmatch(
                    r"bytes \*/(\d+)", exc.headers.get("Content-Range", "")
                )
                try:
                    partial_size = partial.stat().st_size
                except OSError:
                    partial_size = -1
                if match is not None and partial_size == int(match.group(1)):
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
        except http.client.HTTPException as exc:
            self._set_state("failed")
            raise DownloadError(f"HTTP protocol error: {exc}") from exc
        except DownloadPaused:
            self._set_state("paused")
            raise
        except DownloadError:
            if self.state not in {"cancelled", "paused"}:
                self._set_state("failed")
            raise
        except OSError as exc:
            self._set_state("failed")
            raise DownloadError(f"File or network I/O error: {exc}") from exc
