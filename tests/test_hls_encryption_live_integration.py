"""Real FFmpeg coverage for AES-128 HLS and long-running event playlists."""

from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import shutil
import subprocess
import time
from threading import Thread

import pytest

from mediagrab.downloader import DownloadError
from mediagrab.media_stream import MediaStreamTask


FFMPEG = shutil.which("ffmpeg")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg is not installed")
def test_aes128_hls_downloads_and_missing_key_fails_cleanly(tmp_path: Path) -> None:
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
        base = f"http://127.0.0.1:{server.server_port}"
        output = MediaStreamTask(f"{base}/encrypted.m3u8", target, ffmpeg_path=FFMPEG).run()
        assert output.is_file() and output.stat().st_size > 0

        broken = source / "broken.m3u8"
        broken.write_text(
            playlist.read_text(encoding="utf-8").replace('URI="enc.key"', 'URI="missing.key"'),
            encoding="utf-8",
        )
        task = MediaStreamTask(f"{base}/broken.m3u8", target, ffmpeg_path=FFMPEG)
        with pytest.raises(DownloadError):
            task.run()
        assert not (target / "broken.mkv").exists()
        assert not list(target.glob("*.mediagrab-part.*"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg is not installed")
def test_event_playlist_without_endlist_can_be_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "live-source"
    target = tmp_path / "live-target"
    source.mkdir()
    target.mkdir()
    playlist = source / "live.m3u8"
    generated = subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "12", "-c:v", "mpeg2video", "-c:a", "mp2",
        "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
        "-hls_segment_filename", str(source / "segment%02d.ts"), str(playlist),
    ], capture_output=True, text=True)
    if generated.returncode:
        pytest.skip(generated.stderr[-500:])
    lines = [line for line in playlist.read_text(encoding="utf-8").splitlines()
             if line != "#EXT-X-ENDLIST"]
    playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")

    class SlowHandler(QuietHandler):
        def do_GET(self):
            if self.path.endswith(".ts"):
                time.sleep(0.4)
            super().do_GET()

    server = HTTPServer(("127.0.0.1", 0), partial(SlowHandler, directory=str(source)))
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    task = MediaStreamTask(
        f"http://127.0.0.1:{server.server_port}/live.m3u8", target, ffmpeg_path=FFMPEG
    )
    errors = []

    def run_task():
        try:
            task.run()
        except DownloadError as exc:
            errors.append(exc)

    worker = Thread(target=run_task, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while task.state == "queued" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert task.state == "downloading"
        time.sleep(0.6)
        task.cancel()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert errors
        assert task.state == "cancelled"
        assert not (target / "live.mkv").exists()
        assert not list(target.glob("*.mediagrab-part.*"))
    finally:
        if worker.is_alive():
            task.cancel()
            worker.join(timeout=10)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
