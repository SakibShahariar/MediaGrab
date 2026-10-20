"""Tests for bounded manifest fetching and inspection output."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mediagrab.media_inspector import inspect_manifest, format_inspection


HLS = b"""#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",LANGUAGE="en",DEFAULT=YES,URI="audio/en.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English CC",LANGUAGE="en",URI="subs/en.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1920x1080
high/index.m3u8
"""


DASH = b"""<MPD><Period><AdaptationSet mimeType="video/mp4" codecs="avc1">
<Representation id="low" bandwidth="700000" width="640" height="360"><BaseURL>low.mp4</BaseURL></Representation>
<Representation id="high" bandwidth="3000000" width="1920" height="1080"><BaseURL>high.mp4</BaseURL></Representation>
</AdaptationSet></Period></MPD>"""


@pytest.fixture()
def manifest_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/hls"):
                body, content_type = HLS, "application/vnd.apple.mpegurl"
            elif self.path == "/dash":
                body, content_type = DASH, "application/dash+xml"
            elif self.path == "/large":
                body, content_type = b"x" * (4 * 1024 * 1024 + 1), "application/vnd.apple.mpegurl"
            elif self.path == "/html":
                body, content_type = b"<html/>", "text/html"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_inspects_hls_variants_and_alternate_tracks(manifest_server):
    result = inspect_manifest(manifest_server + "/hls?token=secret")
    assert len(result.variants) == 2
    assert result.variants[0].height == 360
    assert result.variants[1].height == 1080
    assert [track.kind for track in result.renditions] == ["audio", "subtitles"]
    rendered = format_inspection(result)
    assert "1920x1080" in rendered
    assert "English CC" in rendered
    assert "token=secret" not in rendered


def test_inspects_dash_representations(manifest_server):
    result = inspect_manifest(manifest_server + "/dash")
    assert len(result.representations) == 2
    assert result.representations[1].height == 1080
    assert result.representations[1].url == manifest_server + "/high.mp4"


@pytest.mark.parametrize("url", [
    "file:///tmp/manifest.m3u8",
    "https://user:pass@example.test/manifest.m3u8",
])
def test_rejects_unsupported_or_credential_urls(url):
    with pytest.raises(ValueError):
        inspect_manifest(url)


def test_rejects_non_manifest_response(manifest_server):
    with pytest.raises(ValueError, match="recognizable HLS or DASH"):
        inspect_manifest(manifest_server + "/html")


def test_rejects_oversized_manifest(manifest_server):
    with pytest.raises(ValueError, match="size limit"):
        inspect_manifest(manifest_server + "/large")


def test_reports_http_errors_without_echoing_url(manifest_server):
    with pytest.raises(ValueError, match="HTTP 404") as exc:
        inspect_manifest(manifest_server + "/missing?token=secret")
    assert "secret" not in str(exc.value)


def test_rejects_nonpositive_timeout():
    with pytest.raises(ValueError, match="timeout must be positive"):
        inspect_manifest("https://example.test/manifest.m3u8", timeout=0)
