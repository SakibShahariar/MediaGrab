"""Input parsing for MediaGrab's command-line interface.

This module has no GTK dependency so command syntax and URL safety can be
tested in headless environments.
"""
from __future__ import annotations

from urllib.parse import urlsplit

_USAGE = (
    "Usage: mediagrab [--add-url|--add-candidate HTTP(S)_URL] | "
    "[--list|--status] | [--pause|--resume|--retry|--cancel QUEUE_ID]"
)


def parse_command(args: list[str]) -> tuple[str, str | None]:
    """Parse one supported CLI operation and validate its argument."""
    if not args:
        return "activate", None
    if len(args) == 1 and args[0] in {"--list", "--status"}:
        return args[0][2:], None
    if len(args) != 2:
        raise ValueError(_USAGE)

    option, value = args
    if option in {"--add-url", "--add-candidate"}:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("MediaGrab accepts only valid HTTP(S) URLs.") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError(
                "MediaGrab accepts only valid HTTP(S) URLs without embedded credentials."
            )
        return option[2:], value

    if option in {"--pause", "--resume", "--retry", "--cancel"}:
        try:
            queue_id = int(value)
        except ValueError as exc:
            raise ValueError("Queue ID must be a positive integer.") from exc
        if queue_id < 1:
            raise ValueError("Queue ID must be a positive integer.")
        return option[2:], str(queue_id)

    raise ValueError(_USAGE)
