"""Tests for the HTTP download core using a local server."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mediagrab.downloader import DownloadError, DownloadTask, filename_from_url


PAYLOAD = b"MediaGrab test payload\\n" * 4096


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/missing":
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        try:
            self.wfile.write(PAYLOAD)
        except BrokenPipeError:
            pass

    def log_message(self, _format: str, *_args: object) -> None:
        pass


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_filename_from_url() -> None:
    assert filename_from_url("https://example.test/files/my%20file.zip?token=abc") == "my file.zip"
    assert filename_from_url("https://example.test/") == "example.test"


def test_rejects_non_http_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        DownloadTask("file:///etc/passwd", tmp_path)


def test_download_writes_file_and_reports_completion(tmp_path: Path, server: str) -> None:
    progress = []
    task = DownloadTask(f"{server}/payload.bin", tmp_path, chunk_size=4096)
    result = task.run(progress.append)

    assert result.name == "payload.bin"
    assert result.read_bytes() == PAYLOAD
    assert task.state == "completed"
    assert progress
    assert progress[-1].state == "completed"
    assert progress[-1].received == len(PAYLOAD)


def test_http_error_is_reported(tmp_path: Path, server: str) -> None:
    task = DownloadTask(f"{server}/missing", tmp_path)
    with pytest.raises(DownloadError, match="HTTP error 404"):
        task.run()
    assert task.state == "failed"


def test_existing_destination_is_not_overwritten(tmp_path: Path, server: str) -> None:
    existing = tmp_path / "payload.bin"
    existing.write_bytes(b"keep me")
    task = DownloadTask(f"{server}/payload.bin", tmp_path)

    with pytest.raises(DownloadError, match="already exists"):
        task.run()

    assert existing.read_bytes() == b"keep me"
