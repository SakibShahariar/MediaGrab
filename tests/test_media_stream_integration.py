"""Optional local end-to-end HLS download test using a real FFmpeg binary."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread

import pytest

from mediagrab.media_stream import MediaStreamTask


FFMPEG = shutil.which("ffmpeg")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg is not installed")
def test_real_ffmpeg_downloads_hls_segments_and_finalizes_output(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    destination = tmp_path / "downloads"
    source_dir.mkdir()
    destination.mkdir()

    playlist = source_dir / "source.m3u8"
    segment_pattern = source_dir / "segment%02d.ts"
    generated = subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
            "-t", "2", "-c:v", "mpeg2video", "-c:a", "mp2",
            "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
            "-hls_segment_filename", str(segment_pattern), str(playlist),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if generated.returncode:
        pytest.skip(f"Installed FFmpeg cannot generate the local HLS fixture: {generated.stderr[-500:]}")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_QuietHandler, directory=str(source_dir)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/source.m3u8"
        task = MediaStreamTask(url, destination, ffmpeg_path=FFMPEG)
        output = task.run()

        assert task.state == "completed"
        assert output == destination / "source.mkv"
        assert output.is_file() and output.stat().st_size > 0
        assert not list(destination.glob("*.mediagrab-part.*"))
        decoded = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(output), "-f", "null", "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert decoded.returncode == 0, decoded.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg is not installed")
def test_real_ffmpeg_handles_aes128_hls_and_missing_key_failure(tmp_path: Path) -> None:
    from mediagrab.downloader import DownloadError

    source_dir = tmp_path / "encrypted-source"
    destination = tmp_path / "encrypted-downloads"
    source_dir.mkdir()
    destination.mkdir()
    key = source_dir / "enc.key"
    key.write_bytes(bytes(range(16)))
    key_info = source_dir / "key-info.txt"
    key_info.write_text(
        f"enc.key\\n{key}\\n00000000000000000000000000000001\\n",
        encoding="utf-8",
    )
    playlist = source_dir / "encrypted.m3u8"
    generated = subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
            "-t", "2", "-c:v", "mpeg2video", "-c:a", "mp2",
            "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
            "-hls_key_info_file", str(key_info),
            "-hls_segment_filename", str(source_dir / "segment%02d.ts"),
            str(playlist),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if generated.returncode:
        pytest.skip(f"Installed FFmpeg cannot generate AES-128 HLS: {generated.stderr[-500:]}")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_QuietHandler, directory=str(source_dir)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        output = MediaStreamTask(
            f"{base_url}/encrypted.m3u8", destination, ffmpeg_path=FFMPEG
        ).run()
        assert output.is_file() and output.stat().st_size > 0

        broken = source_dir / "broken.m3u8"
        broken.write_text(
            playlist.read_text(encoding="utf-8").replace('URI="enc.key"', 'URI="missing.key"'),
            encoding="utf-8",
        )
        task = MediaStreamTask(
            f"{base_url}/broken.m3u8", destination, ffmpeg_path=FFMPEG
        )
        with pytest.raises(DownloadError):
            task.run()
        assert not (destination / "broken.mkv").exists()
        assert not list(destination.glob("*.mediagrab-part.*"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
