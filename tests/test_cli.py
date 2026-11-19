from __future__ import annotations

from pathlib import Path

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


def test_command_line_output_uses_print_literal_with_real_newline() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "mediagrab" / "main.py").read_text(encoding="utf-8")
    assert "command_line.print(" not in source
    assert 'command_line.print_literal(f"{exc}\\n")' in source
    assert 'command_line.print_literal(result + "\\n")' in source

    # The behavioral part needs PyGObject, which CI's plain Python jobs lack.
    pytest.importorskip("gi")
    from mediagrab.main import MediaGrabApplication

    class FakeApp:
        def _execute_external_command(self, action: str, argument: str | None = None) -> str:
            return "help text"

    class FakeCommandLine:
        def __init__(self, args: list[str]) -> None:
            self._args = args
            self.output: list[str] = []

        def get_arguments(self) -> list[str]:
            return self._args

        def print_literal(self, text: str) -> None:
            self.output.append(text)

    help_line = FakeCommandLine(["mediagrab", "--help"])
    assert MediaGrabApplication._on_command_line(FakeApp(), object(), help_line) == 0
    assert len(help_line.output) == 1
    assert help_line.output[0].endswith("\n")

    error_line = FakeCommandLine(["mediagrab", "--delete", "1"])
    assert MediaGrabApplication._on_command_line(FakeApp(), object(), error_line) == 2
    assert len(error_line.output) == 1
    assert error_line.output[0].endswith("\n")
