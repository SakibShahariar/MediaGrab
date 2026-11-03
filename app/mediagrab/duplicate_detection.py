"""Small helpers for pending duplicates and safe completed-file replacement."""

from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from mediagrab.checksum import verify_file


_PENDING_STATUSES = frozenset({
    "Queued",
    "Starting…",
    "Downloading…",
    "Cancelling…",
    "Pausing…",
    "Paused",
})


def has_pending_duplicate(url: str, entries: Iterable[tuple[str, str]]) -> bool:
    """Return whether the exact URL already has a queued or active entry."""
    return any(
        existing_url == url and status in _PENDING_STATUSES
        for existing_url, status in entries
    )


def find_completed_file_duplicates(
    filename: str,
    history: Iterable[dict[str, Any]],
    *,
    expected_checksum: str | None = None,
) -> list[dict[str, Any]]:
    """Find completed history records whose saved file still matches its record.

    A filename and historical-size match is only a candidate signal, not proof
    that two remote resources are byte-for-byte identical.
    """
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        return []

    matches: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict) or entry.get("outcome") != "Completed":
            continue
        if entry.get("filename") != filename:
            continue
        destination = entry.get("destination")
        recorded_size = entry.get("size")
        if (
            not isinstance(destination, str)
            or isinstance(recorded_size, bool)
            or not isinstance(recorded_size, int)
            or recorded_size < 0
        ):
            continue
        path = Path(destination) / filename
        try:
            if not path.is_file() or path.stat().st_size != recorded_size:
                continue
            if expected_checksum is not None:
                # A supplied checksum can rule out a same-name/same-size
                # candidate or positively confirm the saved file's contents.
                verify_file(path, expected_checksum)
            matches.append(entry)
        except (OSError, ValueError):
            continue
    return matches


_REPLACEMENT_SIGNATURE_FIELDS = ("device", "inode", "size", "mtime_ns")


def capture_replace_signature(path: str | Path) -> dict[str, int] | None:
    """Capture the identity of a regular, non-symlink file."""
    try:
        metadata = Path(path).lstat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "size": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
    }


def replace_completed_download(
    downloaded_path: str | Path,
    target_path: str | Path,
    expected_signature: dict[str, int],
) -> None:
    """Atomically replace an unchanged regular file after a complete download.

    A staging file is created beside the target so replacement also works
    across filesystems. The original identity is checked both before and
    after staging; the original is never opened for writing or truncated.
    """
    source = Path(downloaded_path)
    target = Path(target_path)
    if source == target:
        raise ValueError("Replacement source and target must be different files")
    if (
        not isinstance(expected_signature, dict)
        or set(expected_signature) != set(_REPLACEMENT_SIGNATURE_FIELDS)
        or any(
            isinstance(expected_signature[field], bool)
            or not isinstance(expected_signature[field], int)
            for field in _REPLACEMENT_SIGNATURE_FIELDS
        )
    ):
        raise ValueError("Invalid replacement file identity")

    current = capture_replace_signature(target)
    if current is None or current != expected_signature:
        raise OSError("The original file changed or is no longer a regular file; it was preserved")
    if capture_replace_signature(source) is None:
        raise OSError("The completed download is missing or is not a regular file")

    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{target.name}.mediagrab-", suffix=".replace", dir=target.parent
    )
    staging = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as incoming:
            shutil.copyfileobj(incoming, output)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(staging, stat.S_IMODE(target.lstat().st_mode))
        current = capture_replace_signature(target)
        if current is None or current != expected_signature:
            raise OSError("The original file changed while preparing replacement; it was preserved")
        os.replace(staging, target)
        try:
            directory_fd = os.open(
                target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # The atomic rename has already succeeded; do not misreport it as
            # a failed replacement or leave the queue believing the old file exists.
            pass
        try:
            source.unlink(missing_ok=True)
        except OSError:
            # Keeping an extra completed copy is safer than undoing a replacement.
            pass
    except Exception:
        staging.unlink(missing_ok=True)
        raise



def find_completed_url_duplicates(
    redacted_source_url: str,
    history: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find completed history entries for the same already-redacted source URL."""
    if not isinstance(redacted_source_url, str) or not redacted_source_url:
        return []
    return [
        entry
        for entry in history
        if isinstance(entry, dict)
        and entry.get("outcome") == "Completed"
        and entry.get("source_url") == redacted_source_url
    ]
