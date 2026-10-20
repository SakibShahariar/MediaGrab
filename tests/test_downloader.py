"""Tests for the HTTP download core using a local server."""

from __future__ import annotations

import http.client
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


def test_existing_destination_is_preserved_and_download_gets_unique_name(tmp_path: Path, server: str) -> None:
    existing = tmp_path / "payload.bin"
    existing.write_bytes(b"keep me")
    task = DownloadTask(f"{server}/payload.bin", tmp_path)

    result = task.run()

    assert result.name == "payload (1).bin"
    assert existing.read_bytes() == b"keep me"
    assert result.read_bytes() == PAYLOAD



def test_cancel_before_start_does_not_create_destination(tmp_path: Path) -> None:
    destination = tmp_path / "not-created"
    task = DownloadTask("https://example.test/file.bin", destination)
    task.cancel()

    with pytest.raises(DownloadError, match="cancelled before start"):
        task.run()

    assert task.state == "cancelled"
    assert not destination.exists()



def test_resumes_existing_partial_file(tmp_path: Path, server: str) -> None:
    import hashlib
    import json

    url = f"{server}/payload.bin"
    partial = tmp_path / "payload.bin.part"
    offset = len(PAYLOAD) // 3
    partial.write_bytes(PAYLOAD[:offset])
    partial.with_name(f"{partial.name}.json").write_text(json.dumps({
        "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "etag": '"payload-v1"',
        "last_modified": None,
    }), encoding="utf-8")

    task = DownloadTask(url, tmp_path, chunk_size=2048)
    result = task.run()

    assert result.read_bytes() == PAYLOAD
    assert task.state == "completed"
    assert not partial.exists()



def test_download_continues_across_bounded_range_responses(tmp_path: Path) -> None:
    requests = []

    class BoundedRangeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            range_header = self.headers.get("Range")
            requests.append(range_header)
            if not range_header:
                self.send_response(200)
                self.send_header("ETag", '"payload-v1"')
                self.send_header("Content-Length", str(len(PAYLOAD)))
                self.end_headers()
                self.wfile.write(PAYLOAD)
                return

            offset = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            if offset >= len(PAYLOAD):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
                self.end_headers()
                return

            end = min(offset + 1023, len(PAYLOAD) - 1)
            body = PAYLOAD[offset:end + 1]
            self.send_response(206)
            self.send_header("ETag", '"payload-v1"')
            self.send_header("Content-Range", f"bytes {offset}-{end}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), BoundedRangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        partial = tmp_path / "payload.bin.part"
        offset = 19
        partial.write_bytes(PAYLOAD[:offset])
        import hashlib
        import json
        partial.with_name(f"{partial.name}.json").write_text(json.dumps({
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "etag": '"payload-v1"',
            "last_modified": None,
        }), encoding="utf-8")

        result = DownloadTask(url, tmp_path, chunk_size=257).run()

        assert result.read_bytes() == PAYLOAD
        assert len(requests) > 1
        assert requests[0] == f"bytes={offset}-"
        assert requests[1] == f"bytes={offset + 1024}-"
        assert not partial.exists()
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()

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
        import hashlib
        import json

        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(PAYLOAD[:10])
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        partial.with_name(f"{partial.name}.json").write_text(json.dumps({
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "etag": '"payload-v1"',
            "last_modified": None,
        }), encoding="utf-8")
        task = DownloadTask(url, tmp_path)

        with pytest.raises(DownloadError, match="Content-Range for resume"):
            task.run()

        assert partial.read_bytes() == PAYLOAD[:10]
        assert not (tmp_path / "payload.bin").exists()
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()

def test_finalizes_partial_when_server_reports_range_already_complete(tmp_path: Path) -> None:
    class CompleteRangeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), CompleteRangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        import hashlib
        import json

        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(PAYLOAD)
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        partial.with_name(f"{partial.name}.json").write_text(json.dumps({
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "etag": '"payload-v1"',
            "last_modified": None,
        }), encoding="utf-8")
        task = DownloadTask(url, tmp_path)

        result = task.run()

        assert result.read_bytes() == PAYLOAD
        assert task.state == "completed"
        assert not partial.exists()
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_does_not_finalize_partial_when_416_total_does_not_match(tmp_path: Path) -> None:
    class IncompleteRangeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), IncompleteRangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(PAYLOAD[:-1])
        task = DownloadTask(f"http://127.0.0.1:{httpd.server_port}/payload.bin", tmp_path)

        with pytest.raises(DownloadError, match="HTTP error 416"):
            task.run()

        assert partial.read_bytes() == PAYLOAD[:-1]
        assert not (tmp_path / "payload.bin").exists()
        assert task.state == "failed"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()



def test_resume_sends_if_range_from_saved_etag(tmp_path: Path) -> None:
    import hashlib
    import json

    observed = {}

    class ValidatorHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            observed["range"] = self.headers.get("Range")
            observed["if_range"] = self.headers.get("If-Range")
            offset = int(self.headers.get("Range", "bytes=0-").removeprefix("bytes=").split("-", 1)[0])
            body = PAYLOAD[offset:]
            self.send_response(206)
            self.send_header("ETag", '"payload-v1"')
            self.send_header("Content-Range", f"bytes {offset}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ValidatorHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        partial = tmp_path / "payload.bin.part"
        offset = 37
        partial.write_bytes(PAYLOAD[:offset])
        metadata = partial.with_name(f"{partial.name}.json")
        metadata.write_text(json.dumps({
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "etag": '"payload-v1"',
            "last_modified": None,
        }), encoding="utf-8")

        result = DownloadTask(url, tmp_path).run()

        assert observed["range"] == f"bytes={offset}-"
        assert observed["if_range"] == '"payload-v1"'
        assert result.read_bytes() == PAYLOAD
        assert not metadata.exists()
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_does_not_resume_partial_for_different_url(tmp_path: Path) -> None:
    import hashlib
    import json

    observed = {}

    class FreshResponseHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            observed["range"] = self.headers.get("Range")
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FreshResponseHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(b"stale bytes")
        partial.with_name(f"{partial.name}.json").write_text(json.dumps({
            "url_sha256": hashlib.sha256(b"http://different.example/payload.bin").hexdigest(),
            "etag": '"old-version"',
            "last_modified": None,
        }), encoding="utf-8")

        result = DownloadTask(url, tmp_path).run()

        assert observed["range"] is None
        assert result.read_bytes() == PAYLOAD
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_legacy_partial_without_validator_restarts_from_zero(tmp_path: Path) -> None:
    observed = {}

    class NoValidatorHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            observed["range"] = self.headers.get("Range")
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), NoValidatorHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(b"unvalidated old bytes")
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"

        result = DownloadTask(url, tmp_path).run()

        assert observed["range"] is None
        assert result.read_bytes() == PAYLOAD
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_rejects_partial_response_without_requested_range(tmp_path: Path) -> None:
    class UnsolicitedPartialHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = PAYLOAD[:128]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-{len(body) - 1}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), UnsolicitedPartialHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        task = DownloadTask(
            f"http://127.0.0.1:{httpd.server_port}/payload.bin", tmp_path
        )

        with pytest.raises(DownloadError, match="HTTP 206 without a requested byte range"):
            task.run()

        assert not (tmp_path / "payload.bin").exists()
        assert task.state == "failed"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_rejects_invalid_content_length(tmp_path: Path) -> None:
    class InvalidLengthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", "not-a-number")
            self.end_headers()
            self.wfile.write(PAYLOAD)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), InvalidLengthHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        task = DownloadTask(
            f"http://127.0.0.1:{httpd.server_port}/payload.bin", tmp_path
        )

        with pytest.raises(DownloadError, match="invalid Content-Length"):
            task.run()

        assert not (tmp_path / "payload.bin").exists()
        assert task.state == "failed"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_rejects_nonpositive_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout must be positive"):
        DownloadTask("https://example.test/file.bin", tmp_path, timeout=0)


def test_rejects_changed_total_between_range_segments(tmp_path: Path) -> None:
    import hashlib
    import json

    requests = 0

    class ChangingTotalHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            nonlocal requests
            requests += 1
            offset = int(
                self.headers.get("Range", "bytes=0-")
                .removeprefix("bytes=")
                .split("-", 1)[0]
            )
            if requests == 1:
                end = offset + 15
                total = len(PAYLOAD)
            else:
                end = min(offset + 15, len(PAYLOAD) - 1)
                total = len(PAYLOAD) + 1
            body = PAYLOAD[offset:end + 1]
            self.send_response(206)
            self.send_header("ETag", '"payload-v1"')
            self.send_header("Content-Range", f"bytes {offset}-{end}/{total}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ChangingTotalHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        partial = tmp_path / "payload.bin.part"
        partial.write_bytes(PAYLOAD[:8])
        partial.with_name(f"{partial.name}.json").write_text(json.dumps({
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "etag": '"payload-v1"',
            "last_modified": None,
        }), encoding="utf-8")

        with pytest.raises(DownloadError, match="inconsistent Content-Range"):
            DownloadTask(url, tmp_path).run()

        assert not (tmp_path / "payload.bin").exists()
        assert partial.read_bytes() == PAYLOAD[:24]
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()



def test_http_protocol_errors_mark_task_failed(tmp_path: Path, monkeypatch) -> None:
    def broken_response(*_args, **_kwargs):
        raise http.client.IncompleteRead(b"partial", 10)

    monkeypatch.setattr("mediagrab.downloader.urllib.request.urlopen", broken_response)
    task = DownloadTask("https://example.test/file.bin", tmp_path)

    with pytest.raises(DownloadError, match="HTTP protocol error"):
        task.run()

    assert task.state == "failed"


def test_unique_filename_skips_existing_output_and_partial(tmp_path: Path) -> None:
    from mediagrab.downloader import unique_output_path

    (tmp_path / "archive.zip").write_bytes(b"existing")
    (tmp_path / "archive (1).zip.part").write_bytes(b"partial")
    assert unique_output_path(tmp_path, "archive.zip").name == "archive (2).zip"


def test_pause_preserves_partial_and_new_task_resumes(tmp_path: Path) -> None:
    import hashlib
    import json

    class SlowRangeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            offset = 0
            range_header = self.headers.get("Range")
            if range_header:
                offset = int(range_header.removeprefix("bytes=").split("-", 1)[0])
                body = PAYLOAD[offset:]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {offset}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
            else:
                body = PAYLOAD
                self.send_response(200)
            self.send_header("ETag", '"payload-v1"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            for start in range(0, len(body), 512):
                try:
                    self.wfile.write(body[start:start + 512])
                    self.wfile.flush()
                    threading.Event().wait(0.002)
                except (BrokenPipeError, ConnectionResetError):
                    break

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SlowRangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        from mediagrab.downloader import DownloadPaused

        url = f"http://127.0.0.1:{httpd.server_port}/payload.bin"
        task = DownloadTask(url, tmp_path, chunk_size=512, timeout=2)
        paused = False

        def pause_after_first_chunk(progress) -> None:
            nonlocal paused
            if not paused:
                paused = True
                task.pause()

        with pytest.raises(DownloadPaused, match="Download paused"):
            task.run(pause_after_first_chunk)

        partial = tmp_path / "payload.bin.part"
        metadata = partial.with_name(partial.name + ".json")
        assert task.state == "paused"
        assert partial.exists() and 0 < partial.stat().st_size < len(PAYLOAD)
        assert json.loads(metadata.read_text(encoding="utf-8"))["url_sha256"] == hashlib.sha256(url.encode()).hexdigest()

        result = DownloadTask(url, tmp_path, chunk_size=512).run()
        assert result.read_bytes() == PAYLOAD
        assert not partial.exists()
        assert not metadata.exists()
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


@pytest.mark.parametrize("url", ["https://user:secret@example.test/file.bin", "https://[malformed/file.bin", "https:///missing-host.bin"])
def test_rejects_malformed_or_credentialed_urls(tmp_path: Path, url: str) -> None:
    with pytest.raises(ValueError, match="valid HTTP|embedded credentials"):
        DownloadTask(url, tmp_path)
