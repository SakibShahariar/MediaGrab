"""Tests for the browser native-messaging boundary."""
from __future__ import annotations

import io
import json
import struct

import pytest

from mediagrab.native_host import (
    MAX_MESSAGE_BYTES,
    ProtocolError,
    handle_message,
    read_message,
    validate_message,
    write_message,
)


def test_validates_add_url_message() -> None:
    assert validate_message({"version": 1, "type": "add-url", "url": "https://example.test/video.mp4?sig=x"}) == "https://example.test/video.mp4?sig=x"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "https:///missing-host",
    "https://user:secret@example.test/file",
    "",
    12,
])
def test_rejects_unsafe_or_invalid_urls(url: object) -> None:
    with pytest.raises(ProtocolError):
        validate_message({"version": 1, "type": "add-url", "url": url})


@pytest.mark.parametrize("message", [
    None,
    [],
    {"version": 2, "type": "add-url", "url": "https://example.test/a"},
    {"version": 1, "type": "delete-files", "url": "https://example.test/a"},
])
def test_rejects_unknown_message_shapes(message: object) -> None:
    with pytest.raises(ProtocolError):
        validate_message(message)


def test_reads_and_writes_native_message_frame() -> None:
    source = io.BytesIO()
    payload = {"version": 1, "type": "add-url", "url": "https://example.test/a"}
    write_message(source, payload)
    source.seek(0)
    assert read_message(source) == payload
    assert read_message(source) is None


def test_rejects_truncated_and_oversized_frames() -> None:
    with pytest.raises(ProtocolError, match="truncated message length"):
        read_message(io.BytesIO(b"\x01"))
    with pytest.raises(ProtocolError, match="message size"):
        read_message(io.BytesIO(struct.pack("<I", MAX_MESSAGE_BYTES + 1)))


def test_rejects_truncated_body_and_invalid_json() -> None:
    with pytest.raises(ProtocolError, match="truncated message body"):
        read_message(io.BytesIO(struct.pack("<I", 10) + b"{}"))
    payload = b"{bad"
    with pytest.raises(ProtocolError, match="valid UTF-8 JSON"):
        read_message(io.BytesIO(struct.pack("<I", len(payload)) + payload))


def test_handoff_uses_argument_vector_and_does_not_leak_url(monkeypatch) -> None:
    seen = {}

    class Result:
        returncode = 0

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr("mediagrab.native_host.subprocess.run", fake_run)
    url = "https://example.test/file.mp4?signature=secret"
    assert handle_message({"version": 1, "type": "add-url", "url": url}) == {"version": 1, "ok": True}
    assert seen["args"] == ["mediagrab", "--add-url", url]
    assert seen["kwargs"]["shell"] is not True
    assert seen["kwargs"]["stdout"] is not None
