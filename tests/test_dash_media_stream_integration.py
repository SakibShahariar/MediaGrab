"""Optional end-to-end test for a selected DASH SegmentTemplate representation."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread

import pytest

from mediagrab.capture import parse_dash_representations
from mediagrab.media_stream import MediaStreamTask


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="FFmpeg tools are not installed")
def test_selected_dash_representation_downloads_and_finalizes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    mpd = source / "manifest.mpd"
    result = subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "3", "-map", "0:v", "-map", "1:v", "-map", "2:a",
        "-c:v", "mpeg4", "-c:a", "aac", "-f", "dash",
        "-seg_duration", "1", "-adaptation_sets",
        "id=0,streams=0 id=1,streams=1 id=2,streams=2", str(mpd),
    ], capture_output=True, text=True)
    if result.returncode:
        pytest.skip(result.stderr[-500:])

    reps = parse_dash_representations(
        "https://example.test/manifest.mpd", mpd.read_text(encoding="utf-8")
    )
    selected = next(rep for rep in reps if rep.height == 360)
    assert selected.stream_index is not None

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(source)))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/manifest.mpd"
        output = MediaStreamTask(
            url, target, ffmpeg_path=FFMPEG,
            dash_video_stream_index=selected.stream_index,
        ).run()
        probe = subprocess.run([
            FFPROBE, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output),
        ], capture_output=True, text=True)
        assert probe.returncode == 0, probe.stderr
        assert probe.stdout.strip() == "640,360"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
