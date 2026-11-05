from __future__ import annotations

import pytest

from mediagrab.cli import parse_command


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], ("activate", None)),
        (["--help"], ("help", None)),
        (["-h"], ("help", None)),
        (["--list"], ("list", None)),
        (["--status"], ("status", None)),
        (["--add-url", "https://example.test/video.mp4"], ("add-url", "https://example.test/video.mp4")),
        (["--add-candidate", "http://example.test/master.m3u8"], ("add-candidate", "http://example.test/master.m3u8")),
        (["--pause", "2"], ("pause", "2")),
        (["--resume", "3"], ("resume", "3")),
        (["--retry", "4"], ("retry", "4")),
        (["--cancel", "5"], ("cancel", "5")),
    ],
)
def test_parse_supported_commands(args, expected) -> None:
    assert parse_command(args) == expected


@pytest.mark.parametrize(
    "args",
    [
        ["--add-url", "file:///etc/passwd"],
        ["--add-url", "https://user:secret@example.test/file"],
        ["--add-url", "https://[invalid/file"],
        ["--add-url", "https://example.test:invalid/file"],
        ["--add-url", "https://example.test/\nforged"],
        ["--pause", "0"],
        ["--resume", "-1"],
        ["--retry", "one"],
        ["--cancel", "1.5"],
        ["--delete", "1"],
        ["--list", "extra"],
    ],
)
def test_parse_rejects_invalid_commands_and_arguments(args) -> None:
    with pytest.raises(ValueError):
        parse_command(args)



def test_help_text_documents_every_supported_operation() -> None:
    from mediagrab.cli import HELP_TEXT

    for option in (
        "--help", "--add-url", "--add-candidate", "--list", "--status",
        "--pause", "--resume", "--retry", "--cancel",
    ):
        assert option in HELP_TEXT
