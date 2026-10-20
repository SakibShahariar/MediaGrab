"""Select the appropriate transfer engine for a candidate URL."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from mediagrab.capture import MediaKind, classify_media
from mediagrab.downloader import DownloadTask
from mediagrab.media_stream import MediaStreamTask


def create_download_task(
    url: str,
    destination: str | Path,
    *,
    audio_url: str | None = None,
    subtitle_url: str | None = None,
):
    """Create a transfer task, preserving explicitly selected alternate tracks."""
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs with embedded credentials are not accepted")
    kind = classify_media(url)
    if kind in {MediaKind.HLS, MediaKind.DASH} or audio_url or subtitle_url:
        return MediaStreamTask(
            url, destination, audio_url=audio_url, subtitle_url=subtitle_url
        )
    return DownloadTask(url, destination)
