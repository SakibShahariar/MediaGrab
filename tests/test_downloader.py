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
        range_header = self.headers.get("Range")
        body = PAYLOAD
        if range_header and range_header.startswith("bytes="):
            try:
                offset = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            except ValueError:
                self.send_error(400, "Invalid Range")
                return
            if offset >= len(PAYLOAD):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
                self.end_headers()
                return
            body = PAYLOAD[offset:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {offset}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
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



def test_cancel_before_start_does_not_create_destination(tmp_path: Path) -> None:
    destination = tmp_path / "not-created"
    task = DownloadTask("https://example.test/file.bin", destination)
    task.cancel()

    with pytest.raises(DownloadError, match="cancelled before start"):
        task.run()

    assert task.state == "cancelled"
    assert not destination.exists()



def test_resumes_existing_partial_file(tmp_path: Path, server: str) -> None:
    partial = tmp_path / "payload.bin.part"
    offset = len(PAYLOAD) // 3
    partial.write_bytes(PAYLOAD[:offset])

    task = DownloadTask(f"{server}/payload.bin", tmp_path, chunk_size=2048)
    result = task.run()

    assert result.read_bytes() == PAYLOAD
    assert task.state == "completed"
    assert not partial.exists()


def test_server_ignoring_range_restarts_without_duplicate_bytes(tmp_path: Path) -> None:
    class IgnoreRangeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), IgnoreRangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(b"old partial data")
        task = DownloadTask(f"http://127.0.0.1:{httpd.server_port}/payload.bin", tmp_path)
        result = task.run()
        assert result.read_bytes() == PAYLOAD
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()

def test_rejects_inconsistent_content_range_on_resume(tmp_path: Path) -> None:
    class BadRangeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-{len(PAYLOAD) - 2}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(PAYLOAD) - 1))
            self.end_headers()
            self.wfile.write(PAYLOAD[1:])

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), BadRangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(PAYLOAD[:10])
        task = DownloadTask(f"http://127.0.0.1:{httpd.server_port}/payload.bin", tmp_path)

        with pytest.raises(DownloadError, match="invalid Content-Range"):
            task.run()

        assert partial.read_bytes() == PAYLOAD[:10]
        assert not (tmp_path / "payload.bin").exists()
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()

