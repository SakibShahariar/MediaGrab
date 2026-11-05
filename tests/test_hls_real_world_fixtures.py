"""Regression tests using real-world HLS master-playlist fixtures."""

from pathlib import Path

from mediagrab.capture import parse_hls_master_playlist, parse_hls_renditions


FIXTURES = Path(__file__).parent / "fixtures" / "hls"


def _playlist(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_real_world_master_has_multiple_variants_audio_and_subtitles() -> None:
    base = "https://example.test/test-group/playlist.m3u8"
    playlist = _playlist("mtoczko-test-group.m3u8")

    variants = parse_hls_master_playlist(base, playlist)
    renditions = parse_hls_renditions(base, playlist)

    assert [(item.width, item.height) for item in variants] == [
        (960, 540), (1280, 720), (1920, 1080)
    ]
    assert [item.bandwidth for item in variants] == [229254, 261082, 416641]
    assert variants[0].url.endswith("/test-group/video-540/playlist.m3u8")
    assert variants[2].audio_group == "audio-1080"
    assert variants[2].subtitle_group == "text-1080"
    assert len([item for item in renditions if item.kind == "audio"]) == 3
    assert len([item for item in renditions if item.kind == "subtitles"]) == 3
    assert renditions[0].url.endswith("/test-group/text-540/playlist.m3u8")
    assert renditions[3].language == "en"


def test_real_world_shaka_master_has_external_audio_and_subtitles() -> None:
    base = "https://example.test/test-vtt/playlist.m3u8"
    playlist = _playlist("mtoczko-test-vtt.m3u8")

    variants = parse_hls_master_playlist(base, playlist)
    renditions = parse_hls_renditions(base, playlist)

    assert len(variants) == 1
    assert (variants[0].width, variants[0].height) == (480, 360)
    assert variants[0].url.endswith("/test-vtt/h264_360p/main.m3u8")
    assert variants[0].audio_group == "audio"
    assert variants[0].subtitle_group == "text"
    assert [(item.kind, item.name) for item in renditions] == [
        ("audio", "Audio"), ("subtitles", "TIME")
    ]
    assert renditions[0].url.endswith("/test-vtt/audio/main.m3u8")
    assert renditions[1].url.endswith("/test-vtt/text/main.m3u8")
