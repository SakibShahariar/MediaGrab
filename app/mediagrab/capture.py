"""Site-independent classification helpers for browser-observed media URLs.

These helpers inspect metadata and manifest text only; they do not bypass DRM or
other access controls and do not fetch resources themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urljoin, urlparse


class MediaKind(str, Enum):
    DIRECT = "direct"
    HLS = "hls"
    DASH = "dash"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HLSVariant:
    """One variant declared by an HLS master playlist."""

    url: str
    bandwidth: int | None
    width: int | None
    height: int | None
    codecs: str | None


def classify_media(url: str, content_type: str | None = None) -> MediaKind:
    """Classify a candidate using its URL path and optional response MIME type."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return MediaKind.UNKNOWN

    mime = (content_type or "").split(";", 1)[0].strip().lower()
    path = parsed.path.lower()

    if path.endswith(".m3u8") or mime in {
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "audio/mpegurl",
        "audio/x-mpegurl",
    }:
        return MediaKind.HLS
    if path.endswith(".mpd") or mime == "application/dash+xml":
        return MediaKind.DASH
    if mime.startswith(("video/", "audio/")) or path.endswith(
        (".mp4", ".m4v", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav")
    ):
        return MediaKind.DIRECT
    return MediaKind.UNKNOWN


def _parse_attribute_list(value: str) -> dict[str, str]:
    """Parse HLS comma-separated attributes while preserving quoted commas."""
    attributes: dict[str, str] = {}
    for match in re.finditer(r'([A-Z0-9-]+)=("(?:[^"\\]|\\.)*"|[^,]*)', value):
        raw = match.group(2).strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        attributes[match.group(1)] = raw
    return attributes


def parse_hls_master_playlist(base_url: str, playlist: str) -> list[HLSVariant]:
    """Return variants declared by EXT-X-STREAM-INF tags in a master playlist.

    Relative variant URLs are resolved against the playlist URL. Media playlists
    without stream declarations return an empty list.
    """
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be a valid HTTP(S) URL")

    lines = [line.strip() for line in playlist.lstrip("\ufeff").splitlines()]
    if not lines or lines[0] != "#EXTM3U":
        raise ValueError("Not a valid HLS playlist")

    variants: list[HLSVariant] = []
    pending: dict[str, str] | None = None
    for line in lines[1:]:
        if line.startswith("#EXT-X-STREAM-INF:"):
            pending = _parse_attribute_list(line.partition(":")[2])
            continue
        if not line or line.startswith("#") or pending is None:
            continue

        resolution = re.fullmatch(r"(\d+)x(\d+)", pending.get("RESOLUTION", ""))
        bandwidth_text = pending.get("AVERAGE-BANDWIDTH") or pending.get("BANDWIDTH")
        try:
            bandwidth = int(bandwidth_text) if bandwidth_text is not None else None
        except ValueError:
            bandwidth = None
        variants.append(
            HLSVariant(
                url=urljoin(base_url, line),
                bandwidth=bandwidth,
                width=int(resolution.group(1)) if resolution else None,
                height=int(resolution.group(2)) if resolution else None,
                codecs=pending.get("CODECS"),
            )
        )
        pending = None

    return variants
