"""Structured, privacy-safe diagnostics for MediaGrab."""

from __future__ import annotations

import atexit
import json
import logging
import logging.handlers
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mediagrab.url_utils import redact_url


_VALID_LEVELS = {"ERROR", "WARNING", "INFO", "DEBUG"}
_SENSITIVE_KEYS = {
    "authorization", "proxy_authorization", "cookie", "set_cookie",
    "password", "passwd", "token", "access_token", "refresh_token",
    "auth_token", "api_key", "apikey", "secret", "private_key",
}
_URL_KEYS = {"url", "uri", "source_url", "target_url", "from_url", "to_url", "manifest_url"}
_PATH_KEYS = {"path", "destination", "destination_path", "output_path", "directory"}
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_HEADER_PATTERN = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie)\s*:\s*[^\r\n]*"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_SECRET_PATTERN = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|auth[_-]?token|token|"
    r"api[_-]?key|apikey|password|passwd|secret|signature|sig)\s*([=:])\s*([^\s&,;]+)"
)


def default_diagnostics_path() -> Path:
    """Return the per-user XDG state path for rotating diagnostics."""
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    default_home = Path.home() / ".local" / "state"
    state_home = Path(configured).expanduser() if configured else default_home
    if not state_home.is_absolute():
        state_home = default_home
    return state_home / "mediagrab" / "diagnostics.jsonl"


def redact_text(value: str) -> str:
    """Redact signed URLs, secret assignments, auth headers, and personal paths."""
    text = str(value)
    text = _HEADER_PATTERN.sub(lambda match: f"{match.group(1)}: [REDACTED]", text)
    text = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)

    def replace_url(match: re.Match[str]) -> str:
        raw = match.group(0)
        suffix = ""
        while raw and raw[-1] in ".,;:!?)]}":
            suffix = raw[-1] + suffix
            raw = raw[:-1]
        try:
            safe = redact_url(raw)
        except ValueError:
            safe = "[URL]"
        return safe + suffix

    text = _URL_PATTERN.sub(replace_url, text)
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if runtime_dir:
        text = text.replace(runtime_dir, "$XDG_RUNTIME_DIR")
    return text


def redact_value(value: Any, key: str | None = None) -> Any:
    """Recursively redact sensitive fields before they reach the JSON formatter."""
    normalized_key = key.lower().replace("-", "_") if key else ""
    if normalized_key in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        if normalized_key in _URL_KEYS:
            try:
                return redact_url(value)
            except ValueError:
                return "[URL]"
        if normalized_key in _PATH_KEYS and Path(value).is_absolute():
            return f"[PATH]/{Path(value).name}" if Path(value).name else "[PATH]"
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))


class RedactingJsonFormatter(logging.Formatter):
    """Emit one compact JSON object per event, with a final redaction pass."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", record.getMessage())
        fields = getattr(record, "fields", {})
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "component": record.name.removeprefix("mediagrab."),
            "event": redact_text(str(event)),
            "fields": redact_value(fields if isinstance(fields, dict) else {"value": fields}),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _PrivateRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Create the active and rotated log files with owner-only permissions."""

    def _open(self):
        descriptor = os.open(
            self.baseFilename,
            os.O_CREAT | os.O_APPEND | os.O_WRONLY,
            0o600,
        )
        return os.fdopen(descriptor, self.mode, encoding=self.encoding, errors=self.errors)


_logger = logging.getLogger("mediagrab")
_file_handler: _PrivateRotatingFileHandler | None = None
_log_path: Path | None = None
_lock = threading.RLock()


def configure_logging(level: str = "INFO", path: str | Path | None = None) -> logging.Logger:
    """Configure small rotating JSONL logs; callers can change verbosity at runtime."""
    global _file_handler, _log_path
    normalized = str(level).upper()
    if normalized not in _VALID_LEVELS:
        normalized = "INFO"
    target = Path(path) if path is not None else default_diagnostics_path()

    with _lock:
        if _file_handler is not None and _log_path == target:
            _logger.setLevel(getattr(logging, normalized))
            return _logger
        shutdown_logging()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = _PrivateRotatingFileHandler(
            target, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"
        )
        try:
            os.chmod(target, 0o600)
        except OSError:
            handler.close()
            raise
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(RedactingJsonFormatter())
        _logger.handlers.clear()
        _logger.addHandler(handler)
        _logger.setLevel(getattr(logging, normalized))
        _logger.propagate = False
        _file_handler = handler
        _log_path = target
        return _logger


def get_logger(component: str) -> logging.Logger:
    """Return a component logger beneath the configured MediaGrab logger."""
    return logging.getLogger(f"mediagrab.{component}")


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Record a structured event. Avoid calling this for per-chunk progress."""
    logger.log(level, event, extra={"event": event, "fields": fields})


def read_diagnostics(
    path: str | Path | None = None,
    *,
    max_bytes: int = 1024 * 1024,
) -> str:
    """Read recent logs for user export/copy; redact once more before returning."""
    target = Path(path) if path is not None else default_diagnostics_path()
    with _lock:
        if _file_handler is not None:
            _file_handler.flush()
        files = [target, Path(f"{target}.1"), Path(f"{target}.2")]
        newest_first: list[str] = []
        remaining = max(1, max_bytes)
        for file_path in files:
            try:
                data = file_path.read_bytes()
            except OSError:
                continue
            if len(data) > remaining:
                data = data[-remaining:]
            newest_first.append(data.decode("utf-8", errors="replace"))
            remaining -= len(data)
            if remaining <= 0:
                break
    return redact_text("".join(reversed(newest_first)))


def shutdown_logging() -> None:
    """Flush and close the diagnostics handler, primarily for tests and process exit."""
    global _file_handler, _log_path
    with _lock:
        for handler in list(_logger.handlers):
            _logger.removeHandler(handler)
            try:
                handler.flush()
            finally:
                handler.close()
        _file_handler = None
        _log_path = None


atexit.register(shutdown_logging)
