"""Streaming checksum validation for completed download files."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_ALGORITHMS = {"md5": 32, "sha1": 40, "sha256": 64}


class ChecksumMismatchError(ValueError):
    """Raised when a downloaded file does not match its expected digest."""


def parse_expected_checksum(value: str) -> tuple[str, str]:
    """Parse an algorithm:hex-digest checksum supplied by the caller."""
    if not isinstance(value, str) or ":" not in value:
        raise ValueError("Checksum must use algorithm:hex-digest format")
    algorithm, digest = value.strip().lower().split(":", 1)
    if algorithm not in _ALGORITHMS:
        raise ValueError("Checksum algorithm must be SHA-256, SHA-1, or MD5")
    if re.fullmatch(r"[0-9a-f]+", digest) is None or len(digest) != _ALGORITHMS[algorithm]:
        raise ValueError(f"Invalid {algorithm.upper()} checksum digest")
    return algorithm, digest


def verify_file(path: str | Path, expected_checksum: str) -> str:
    """Hash a file in bounded memory and raise when it differs from the expected digest."""
    algorithm, expected = parse_expected_checksum(expected_checksum)
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ChecksumMismatchError(
            f"{algorithm.upper()} checksum mismatch (expected {expected}, got {actual})"
        )
    return actual
