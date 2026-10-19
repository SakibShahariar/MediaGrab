"""Tests for site-independent media classification and HLS parsing."""

from __future__ import annotations

import pytest

from mediagrab.capture import MediaKind, classify_media, parse_hls_master_playlist


@pytest.mark.parametrize(
    ("url", "content_type", "expected"),
    [
        ("https://cdn.example/video.mp4?token=secret", None, MediaKind.DIRECT),
        ("https://cdn.example/stream", "video/mp4; codecs=avc1", MediaKind.DIRECT),
        ("https://cdn.example/master.m3u8?x=1", None, MediaKind.HLS),
        ("https://cdn.example/live", "application/vnd.apple.mpegurl", MediaKind.HLS),
        ("https://cdn.example/manifest.mpd", None, MediaKind.DASH),
        ("https://cdn.example/manifest", "application/dash+xml", MediaKind.DASH),
        ("https://example.test/page", "text/html; charset=utf-8", MediaKind.UNKNOWN),
        ("file:///tmp/video.mp4", "video/mp4", MediaKind.UNKNOWN),
    ],
)
def test_classifies_media_candidates(url, content_type, expected) -> None:
    assert classify_media(url, content_type) is expected


def test_parses_hls_variants_and_resolves_relative_urls() -> None:
    playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2"
low/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,AVERAGE-BANDWIDTH=2200000,RESOLUTION=1280x720
../high/index.m3u8
"""
    variants = parse_hls_master_playlist(
        "https://cdn.example/media/master.m3u8", playlist
    )

    assert len(variants) == 2
    assert variants[0].url == "https://cdn.example/media/low/index.m3u8"
    assert variants[0].bandwidth == 800000
    assert (variants[0].width, variants[0].height) == (640, 360)
    assert variants[0].codecs == "avc1.4d401e,mp4a.40.2"
    assert variants[1].url == "https://cdn.example/high/index.m3u8"
    assert variants[1].bandwidth == 2200000
    assert (variants[1].width, variants[1].height) == (1280, 720)


def test_media_playlist_has_no_variants() -> None:
    playlist = """#EXTM3U
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
segment-001.ts
"""
    assert parse_hls_master_playlist(
        "https://cdn.example/live/index.m3u8", playlist
    ) == []


def test_rejects_invalid_playlist_and_base_url() -> None:
    with pytest.raises(ValueError, match="Not a valid HLS playlist"):
        parse_hls_master_playlist("https://cdn.example/master.m3u8", "not a playlist")
    with pytest.raises(ValueError, match="valid HTTP"):
        parse_hls_master_playlist("file:///tmp/master.m3u8", "#EXTM3U")
