"""Tests for optional expected-checksum verification."""
from __future__ import annotations

import hashlib

import pytest

from mediagrab.checksum import ChecksumMismatchError, parse_expected_checksum, verify_file
from mediagrab.downloader import DownloadError, DownloadTask


def test_parse_supported_checksum_algorithms() -> None:
    for algorithm, digest in (("md5", "0" * 32), ("sha1", "0" * 40), ("sha256", "0" * 64)):
        assert parse_expected_checksum(f"{algorithm}:{digest}") == (algorithm, digest)


@pytest.mark.parametrize("value", ["", "sha512:" + "0" * 128, "sha256:xyz", "md5:abcd"])
def test_rejects_invalid_expected_checksum(value: str) -> None:
    with pytest.raises(ValueError, match="Checksum|checksum|digest"):
        parse_expected_checksum(value)


def test_verify_file_matches_and_reports_mismatch(tmp_path) -> None:
    payload = b"MediaGrab checksum fixture"
    path = tmp_path / "payload.bin"
    path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()

    assert verify_file(path, f"sha256:{expected}") == expected
    with pytest.raises(ChecksumMismatchError, match="SHA256 checksum mismatch"):
        verify_file(path, "sha256:" + "0" * 64)


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_download_task_verifies_before_finalizing(tmp_path, monkeypatch) -> None:
    payload = b"verified download"
    monkeypatch.setattr(
        "mediagrab.downloader.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    expected = hashlib.sha256(payload).hexdigest()
    task = DownloadTask(
        "https://cdn.test/payload.bin", tmp_path,
        expected_checksum=f"sha256:{expected}",
    )

    target = task.run()

    assert target.read_bytes() == payload
    assert task.state == "completed"


def test_checksum_mismatch_never_creates_completed_file(tmp_path, monkeypatch) -> None:
    payload = b"tampered download"
    monkeypatch.setattr(
        "mediagrab.downloader.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    task = DownloadTask(
        "https://cdn.test/payload.bin", tmp_path,
        expected_checksum="sha256:" + "0" * 64,
    )

    with pytest.raises(DownloadError, match="Checksum verification failed.*SHA256 checksum mismatch"):
        task.run()

    assert not (tmp_path / "payload.bin").exists()
    assert (tmp_path / "payload.bin.part").read_bytes() == payload
    assert task.state == "failed"
