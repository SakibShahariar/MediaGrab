"""Tests for site-independent media classification and HLS parsing."""

from __future__ import annotations

import pytest

from mediagrab.capture import (
    MediaKind,
    classify_media,
    parse_dash_representations,
    parse_hls_master_playlist,
    parse_hls_renditions,
)


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
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2",AUDIO="audio",SUBTITLES="subs"
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
    assert variants[0].audio_group == "audio"
    assert variants[0].subtitle_group == "subs"
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



def test_parses_namespaced_dash_representations_and_inherited_metadata() -> None:
    manifest = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet mimeType="video/mp4" codecs="avc1.640028">
      <Representation id="low" bandwidth="800000" width="640" height="360">
        <BaseURL>video/low.mp4</BaseURL>
      </Representation>
      <Representation id="high" bandwidth="2500000" width="1920" height="1080">
        <BaseURL>https://cdn.example/high.mp4</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet mimeType="audio/mp4" codecs="mp4a.40.2">
      <Representation id="audio" bandwidth="128000">
        <BaseURL>audio/en.m4a</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""
    reps = parse_dash_representations("https://cdn.example/manifests/movie.mpd", manifest)
    assert len(reps) == 3
    assert reps[0].url == "https://cdn.example/manifests/video/low.mp4"
    assert (reps[0].width, reps[0].height, reps[0].bandwidth) == (640, 360, 800000)
    assert reps[0].mime_type == "video/mp4"
    assert reps[0].codecs == "avc1.640028"
    assert reps[1].url == "https://cdn.example/high.mp4"
    assert reps[2].url == "https://cdn.example/manifests/audio/en.m4a"
    assert reps[2].mime_type == "audio/mp4"
    assert reps[2].codecs == "mp4a.40.2"


def test_dash_template_representation_does_not_claim_direct_file_url() -> None:
    manifest = """<MPD><Period><AdaptationSet mimeType="video/mp4">
      <Representation id="v1" bandwidth="900000">
        <SegmentTemplate media="chunk-$Number$.m4s" initialization="init.mp4"/>
      </Representation>
    </AdaptationSet></Period></MPD>"""
    reps = parse_dash_representations("https://cdn.example/movie.mpd", manifest)
    assert len(reps) == 1
    assert reps[0].url is None
    assert reps[0].id == "v1"
    assert reps[0].mime_type == "video/mp4"


def test_dash_rejects_invalid_xml_and_non_mpd_documents() -> None:
    with pytest.raises(ValueError, match="Invalid DASH XML"):
        parse_dash_representations("https://cdn.example/movie.mpd", "<MPD>")
    with pytest.raises(ValueError, match="Not a DASH MPD"):
        parse_dash_representations("https://cdn.example/movie.mpd", "<html/>")
    with pytest.raises(ValueError, match="valid HTTP"):
        parse_dash_representations("file:///tmp/movie.mpd", "<MPD/>")


def test_dash_manifest_without_representations_returns_empty_list() -> None:
    assert parse_dash_representations(
        "https://cdn.example/movie.mpd", "<MPD><Period/></MPD>"
    ) == []



def test_parses_hls_audio_and_subtitle_renditions() -> None:
    playlist = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",LANGUAGE="en",DEFAULT=YES,AUTOSELECT=YES,URI="audio/en.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English CC",LANGUAGE="en",DEFAULT=YES,AUTOSELECT=YES,FORCED=NO,URI="../subs/en.vtt"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Japanese",LANGUAGE="ja",URI="https://cdn.example/ja.m3u8"
#EXT-X-MEDIA:TYPE=CLOSED-CAPTIONS,GROUP-ID="cc",NAME="CC1",INSTREAM-ID="CC1"
"""
    tracks = parse_hls_renditions("https://cdn.example/show/master.m3u8", playlist)
    assert len(tracks) == 3
    assert tracks[0].kind == "audio"
    assert tracks[0].url == "https://cdn.example/show/audio/en.m3u8"
    assert tracks[0].language == "en"
    assert tracks[0].is_default and tracks[0].autoselect
    assert tracks[1].kind == "subtitles"
    assert tracks[1].url == "https://cdn.example/subs/en.vtt"
    assert tracks[1].name == "English CC"
    assert tracks[1].forced is False
    assert tracks[2].url == "https://cdn.example/ja.m3u8"
    assert tracks[2].language == "ja"


def test_hls_renditions_allow_tracks_without_separate_uri() -> None:
    playlist = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Main",DEFAULT=YES
"""
    tracks = parse_hls_renditions("https://cdn.example/master.m3u8", playlist)
    assert len(tracks) == 1
    assert tracks[0].url is None


def test_hls_renditions_reject_invalid_playlist() -> None:
    with pytest.raises(ValueError, match="Not a valid HLS playlist"):
        parse_hls_renditions("https://cdn.example/master.m3u8", "not a playlist")


def test_hls_renditions_accept_utf8_bom() -> None:
    playlist = chr(0xFEFF) + "#EXTM3U" + chr(10) + '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",URI="audio/en.m3u8"' + chr(10)
    tracks = parse_hls_renditions("https://cdn.example/master.m3u8", playlist)
    assert len(tracks) == 1
    assert tracks[0].url == "https://cdn.example/audio/en.m3u8"
