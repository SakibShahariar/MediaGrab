"""Input parsing for MediaGrab's command-line interface.

This module has no GTK dependency so command syntax and URL safety can be
tested in headless environments.
"""
from __future__ import annotations

from mediagrab.url_utils import is_valid_http_url

_USAGE = (
    "Usage: mediagrab [--help] | [--add-url|--add-candidate HTTP(S)_URL] | "
    "[--list|--status] | [--pause|--resume|--retry|--cancel QUEUE_ID]"
)


def parse_command(args: list[str]) -> tuple[str, str | None]:
    """Parse one supported CLI operation and validate its argument."""
    if not args:
        return "activate", None
    if len(args) == 1 and args[0] in {"--help", "-h"}:
        return "help", None
    if len(args) == 1 and args[0] in {"--list", "--status"}:
        return args[0][2:], None
    if len(args) != 2:
        raise ValueError(_USAGE)

    option, value = args
    if option in {"--add-url", "--add-candidate"}:
        if not is_valid_http_url(value):
            raise ValueError(
                "MediaGrab accepts only valid credential-free HTTP(S) URLs."
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
