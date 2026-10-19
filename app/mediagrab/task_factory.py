"""Select the appropriate transfer engine for a candidate URL."""

from __future__ import annotations

from pathlib import Path

from mediagrab.capture import MediaKind, classify_media
from mediagrab.downloader import DownloadTask
from mediagrab.media_stream import MediaStreamTask


def create_download_task(url: str, destination: str | Path):
    """Create a direct-file or FFmpeg-backed task based on the URL path.

    Unknown URLs remain eligible for direct HTTP downloads because servers often
    omit useful file extensions.
    """
    kind = classify_media(url)
    if kind in {MediaKind.HLS, MediaKind.DASH}:
        return MediaStreamTask(url, destination)
    return DownloadTask(url, destination)
