"""Tests for the browser native-messaging boundary."""
from __future__ import annotations

import io
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from mediagrab.native_host import (
    MAX_MESSAGE_BYTES,
    ProtocolError,
    handle_message,
    read_message,
    validate_message,
    write_message,
)


@pytest.mark.parametrize("message_type", ["add-url", "add-candidate"])
def test_validates_supported_url_messages(message_type: str) -> None:
    assert validate_message({"version": 1, "type": message_type, "url": "https://example.test/video.mp4?sig=x"}) == "https://example.test/video.mp4?sig=x"



def test_rejects_unhashable_message_type() -> None:
    with pytest.raises(ProtocolError, match="unsupported message type"):
        validate_message({"version": 1, "type": [], "url": "https://example.test/video.mp4"})


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


@pytest.mark.parametrize(
    ("message_type", "argument"),
    [("add-url", "--add-url"), ("add-candidate", "--add-candidate")],
)
def test_handoff_uses_argument_vector_and_does_not_leak_url(
    monkeypatch, message_type: str, argument: str
) -> None:
    seen = {}

    class Result:
        returncode = 0

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr("mediagrab.native_host.subprocess.run", fake_run)
    url = "https://example.test/file.mp4?signature=secret"
    assert handle_message({"version": 1, "type": message_type, "url": url}) == {"version": 1, "ok": True}
    assert seen["args"] == ["mediagrab", argument, url]
    assert "shell" not in seen["kwargs"]
    assert seen["kwargs"]["stdout"] is not None



@pytest.mark.parametrize(
    ("message_type", "expected_argument"),
    [("add-url", "--add-url"), ("add-candidate", "--add-candidate")],
)
def test_native_host_process_frames_and_hands_off_to_desktop(
    tmp_path: Path, message_type: str, expected_argument: str
) -> None:
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    capture_path = tmp_path / "arguments.json"
    executable = binary_directory / "mediagrab"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["MEDIAGRAB_CAPTURE"], "w", encoding="utf-8") as output:
    json.dump(sys.argv[1:], output)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    url = "https://media.example.test/master.m3u8?signature=private"
    payload = json.dumps({
        "version": 1,
        "type": message_type,
        "url": url,
    }).encode("utf-8")
    environment = os.environ.copy()
    environment["PATH"] = str(binary_directory) + os.pathsep + environment.get("PATH", "")
    environment["MEDIAGRAB_CAPTURE"] = str(capture_path)

    result = subprocess.run(
        [sys.executable, "-m", "mediagrab.native_host"],
        input=struct.pack("<I", len(payload)) + payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == b""
    response_length = struct.unpack("<I", result.stdout[:4])[0]
    response = json.loads(result.stdout[4:4 + response_length])
    assert response == {"version": 1, "ok": True}
    assert json.loads(capture_path.read_text(encoding="utf-8")) == [
        expected_argument,
        url,
    ]
