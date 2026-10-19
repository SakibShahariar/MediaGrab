"""Browser native-messaging protocol and safe MediaGrab handoff.

The host is deliberately GTK-free. Browser input is untrusted and is never
interpreted as a shell command; the application is launched with an argv list.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from typing import BinaryIO
from urllib.parse import urlsplit

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024
HOST_NAME = "io.github.SakibShahariar.MediaGrab"


class ProtocolError(ValueError):
    """Invalid or unsupported native-messaging input."""


def validate_message(message: object) -> str:
    """Return the URL from a supported add-url message or reject it."""
    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")
    if message.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    if message.get("type") != "add-url":
        raise ProtocolError("unsupported message type")
    url = message.get("url")
    if not isinstance(url, str) or not url or len(url) > 16_384:
        raise ProtocolError("url must be a non-empty string of at most 16384 characters")
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise ProtocolError("malformed URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProtocolError("only HTTP(S) URLs are accepted")
    if parsed.username is not None or parsed.password is not None:
        raise ProtocolError("URLs containing embedded credentials are not accepted")
    if any(ord(char) < 32 for char in url):
        raise ProtocolError("URL contains control characters")
    return url


def read_message(stream: BinaryIO) -> object | None:
    """Read one Chrome/Firefox native-messaging frame; None means clean EOF."""
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ProtocolError("truncated message length")
    length = struct.unpack("<I", header)[0]
    if length == 0 or length > MAX_MESSAGE_BYTES:
        raise ProtocolError("message size is invalid")
    payload = stream.read(length)
    if len(payload) != length:
        raise ProtocolError("truncated message body")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("message is not valid UTF-8 JSON") from exc


def write_message(stream: BinaryIO, message: dict[str, object]) -> None:
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(payload)))
    stream.write(payload)
    stream.flush()


def handle_message(message: object, *, executable: str = "mediagrab") -> dict[str, object]:
    """Validate and ask the single-instance desktop app to enqueue a URL."""
    url = validate_message(message)
    try:
        result = subprocess.run(
            [executable, "--add-url", url],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"version": PROTOCOL_VERSION, "ok": False, "error": "Could not contact MediaGrab"}
    if result.returncode:
        # Do not echo URLs or subprocess output: either may contain signed tokens.
        return {"version": PROTOCOL_VERSION, "ok": False, "error": "MediaGrab rejected the request"}
    return {"version": PROTOCOL_VERSION, "ok": True}


def main() -> int:
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    try:
        while True:
            message = read_message(source)
            if message is None:
                return 0
            try:
                response = handle_message(message)
            except ProtocolError as exc:
                response = {"version": PROTOCOL_VERSION, "ok": False, "error": str(exc)}
            write_message(sink, response)
    except ProtocolError:
        # stdout is reserved for native-messaging frames; diagnostics go to stderr.
        print("MediaGrab native host: malformed input frame", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
