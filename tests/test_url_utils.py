"""Tests for privacy-safe URL previews."""

import pytest

from mediagrab.url_utils import redact_url


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
