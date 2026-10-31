"""Tests for privacy-safe URL previews."""

import pytest

from mediagrab.url_utils import is_valid_http_url, redact_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://cdn.example/video.mp4", "https://cdn.example/video.mp4"),
        ("https://cdn.example/video.mp4?token=secret&expires=123", "https://cdn.example/video.mp4?…"),
        ("https://cdn.example/live.m3u8?sig=secret#key=private", "https://cdn.example/live.m3u8?…#…"),
        ("https://example.test/path?x=1", "https://example.test/path?…"),
    ],
)
def test_redacts_query_and_fragment_values(url: str, expected: str) -> None:
    assert redact_url(url) == expected


def test_empty_url_is_safe() -> None:
    assert redact_url("") == ""


def test_redacts_embedded_userinfo_and_signed_query() -> None:
    assert redact_url("https://alice:secret@cdn.example/file.mp4?token=private") == "https://cdn.example/file.mp4?…"



@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/video.mp4",
        "http://localhost:8000/file.bin",
        "https://[::1]:8443/stream.m3u8",
    ],
)
def test_accepts_valid_http_urls(url: str) -> None:
    assert is_valid_http_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///etc/passwd",
        "ftp://example.test/file",
        "https://user:secret@example.test/file",
        "https://[invalid/file",
        "https://example.test:invalid/file",
        "https://example.test/\nforged",
        "javascript:alert(1)",
    ],
)
def test_rejects_invalid_or_credentialed_http_urls(url: str) -> None:
    assert not is_valid_http_url(url)


def test_rejects_non_string_clipboard_values() -> None:
    assert not is_valid_http_url(None)
    assert not is_valid_http_url(123)
