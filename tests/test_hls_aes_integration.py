"""Real FFmpeg integration for standard AES-128 HLS encryption."""

from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import shutil
import subprocess
from threading import Thread

import pytest

from mediagrab.media_stream import MediaStreamTask


FFMPEG = shutil.which("ffmpeg")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg is not installed")
def test_aes128_hls_downloads_and_finalizes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    key = source / "enc.key"
    key.write_bytes(bytes(range(16)))
    info = source / "key-info.txt"
    info.write_text("\n".join([
        "enc.key", str(key), "00000000000000000000000000000001", "",
    ]), encoding="utf-8")
    playlist = source / "encrypted.m3u8"
    generated = subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
        "-t", "2", "-c:v", "mpeg2video", "-c:a", "mp2",
        "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
        "-hls_key_info_file", str(info),
        "-hls_segment_filename", str(source / "segment%02d.ts"), str(playlist),
    ], capture_output=True, text=True)
    if generated.returncode:
        pytest.skip(generated.stderr[-500:])

    server = HTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(source)))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/encrypted.m3u8"
        output = MediaStreamTask(url, target, ffmpeg_path=FFMPEG).run()
        assert output.is_file() and output.stat().st_size > 0
        decoded = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(output), "-f", "null", "-"],
            capture_output=True, text=True,
        )
        assert decoded.returncode == 0, decoded.stderr
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
