"""Tests for structured, privacy-safe diagnostics."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mediagrab.diagnostics import (
    configure_logging, get_logger, log_event, read_diagnostics,
    redact_text, redact_value, shutdown_logging,
)


def test_redacts_urls_headers_tokens_and_home_paths(monkeypatch) -> None:
    home = str(Path.home())
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/4242")
    value = (
        "GET https://cdn.example.test/video.m3u8?token=secret&sig=private#key=hidden "
        "Authorization: Bearer abc123 Cookie: session=xyz "
        f"path={home}/Downloads/video.mp4 runtime=/run/user/4242/app"
    )
    redacted = redact_text(value)
    for secret in ("secret", "private", "hidden", "abc123", "session=xyz", home, "/run/user/4242"):
        assert secret not in redacted
    assert "https://cdn.example.test/video.m3u8?…" in redacted


def test_redact_value_handles_nested_sensitive_fields_and_paths(tmp_path: Path) -> None:
    result = redact_value({
        "url": "https://example.test/file.mp4?token=secret",
        "headers": {"Authorization": "Bearer abc", "Content-Type": "video/mp4"},
        "destination": str(tmp_path / "private" / "file.mp4"),
        "items": [{"access_token": "hidden"}],
    })
    assert result["url"] == "https://example.test/file.mp4?…"
    assert result["headers"]["Authorization"] == "[REDACTED]"
    assert result["headers"]["Content-Type"] == "video/mp4"
    assert result["destination"] == "[PATH]/file.mp4"
    assert result["items"][0]["access_token"] == "[REDACTED]"


def test_structured_json_logs_are_redacted_and_private(tmp_path: Path) -> None:
    path = tmp_path / "state" / "diagnostics.jsonl"
    try:
        configure_logging("DEBUG", path)
        log_event(
            get_logger("test"),
            "download_started",
            url="https://cdn.example.test/file.mp4?sig=secret",
            headers={"Cookie": "session=private"},
            destination=str(tmp_path / "Downloads" / "file.mp4"),
            attempt=2,
        )
        text = read_diagnostics(path)
        record = json.loads(text.strip().splitlines()[-1])
        assert record["event"] == "download_started"
        assert record["component"] == "test"
        assert record["fields"]["url"] == "https://cdn.example.test/file.mp4?…"
        assert record["fields"]["headers"]["Cookie"] == "[REDACTED]"
        assert record["fields"]["destination"] == "[PATH]/file.mp4"
        assert "secret" not in text and "private" not in text
        assert path.stat().st_mode & 0o077 == 0
        assert path.parent.stat().st_mode & 0o077 == 0
    finally:
        shutdown_logging()


def test_verbosity_filters_events(tmp_path: Path) -> None:
    path = tmp_path / "diagnostics.jsonl"
    try:
        configure_logging("WARNING", path)
        log_event(get_logger("test"), "hidden_info", level=logging.INFO)
        log_event(get_logger("test"), "visible_warning", level=logging.WARNING)
        text = read_diagnostics(path)
        assert "visible_warning" in text
        assert "hidden_info" not in text
        configure_logging("DEBUG", path)
        log_event(get_logger("test"), "visible_debug", level=logging.DEBUG)
        assert "visible_debug" in read_diagnostics(path)
    finally:
        shutdown_logging()


def test_relative_xdg_state_home_uses_safe_default(monkeypatch) -> None:
    from mediagrab.diagnostics import default_diagnostics_path

    monkeypatch.setenv("XDG_STATE_HOME", "relative-state")
    assert default_diagnostics_path() == (
        Path.home() / ".local" / "state" / "mediagrab" / "diagnostics.jsonl"
    )
