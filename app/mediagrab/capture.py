"""Site-independent classification helpers for browser-observed media URLs.

These helpers inspect metadata and manifest text only; they do not bypass DRM or
other access controls and do not fetch resources themselves.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urljoin, urlparse


class MediaKind(str, Enum):
    DIRECT = "direct"
    HLS = "hls"
    DASH = "dash"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HLSRendition:
    """An alternate HLS audio or subtitle track."""

    kind: str
    group_id: str | None
    name: str | None
    language: str | None
    url: str | None
    is_default: bool
    autoselect: bool
    forced: bool


@dataclass(frozen=True)
class DASHRepresentation:
    """DASH representation metadata; url is set only for an explicit BaseURL."""

    id: str | None
    url: str | None
    bandwidth: int | None
    width: int | None
    height: int | None
    mime_type: str | None
    codecs: str | None


@dataclass(frozen=True)
class HLSVariant:
    """One variant declared by an HLS master playlist."""

    url: str
    bandwidth: int | None
    width: int | None
    height: int | None
    codecs: str | None
    audio_group: str | None = None
    subtitle_group: str | None = None


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



def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _nonnegative_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_dash_representations(
    manifest_url: str, manifest: str
) -> list[DASHRepresentation]:
    """Parse DASH representation metadata without downloading media segments.

    Namespace-qualified MPDs and AdaptationSet-inherited MIME/codecs are
    supported. A representation URL is returned only when that representation
    declares an explicit BaseURL; template-based streams need a segment engine.
    """
    parsed = urlparse(manifest_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("manifest_url must be a valid HTTP(S) URL")
    try:
        root = ET.fromstring(manifest)
    except ET.ParseError as exc:
        raise ValueError("Invalid DASH XML manifest") from exc
    if _xml_local_name(root.tag) != "MPD":
        raise ValueError("Not a DASH MPD manifest")

    def find_base(element: ET.Element, parent: str) -> str:
        for child in element:
            if _xml_local_name(child.tag) == "BaseURL" and child.text and child.text.strip():
                return urljoin(parent, child.text.strip())
        return parent

    mpd_base = find_base(root, manifest_url)
    result: list[DASHRepresentation] = []
    for period in root:
        if _xml_local_name(period.tag) != "Period":
            continue
        period_base = find_base(period, mpd_base)
        for adaptation in period:
            if _xml_local_name(adaptation.tag) != "AdaptationSet":
                continue
            adaptation_base = find_base(adaptation, period_base)
            for representation in adaptation:
                if _xml_local_name(representation.tag) != "Representation":
                    continue
                own_base = next(
                    (
                        child.text.strip()
                        for child in representation
                        if _xml_local_name(child.tag) == "BaseURL"
                        and child.text
                        and child.text.strip()
                    ),
                    None,
                )
                attrs = representation.attrib
                result.append(
                    DASHRepresentation(
                        id=attrs.get("id"),
                        url=urljoin(adaptation_base, own_base) if own_base else None,
                        bandwidth=_nonnegative_int(attrs.get("bandwidth")),
                        width=_nonnegative_int(attrs.get("width")),
                        height=_nonnegative_int(attrs.get("height")),
                        mime_type=attrs.get("mimeType") or adaptation.attrib.get("mimeType"),
                        codecs=attrs.get("codecs") or adaptation.attrib.get("codecs"),
                    )
                )
    return result


def _parse_attribute_list(value: str) -> dict[str, str]:
    """Parse HLS comma-separated attributes while preserving quoted commas."""
    attributes: dict[str, str] = {}
    for match in re.finditer(r'([A-Z0-9-]+)=("(?:[^"\\]|\\.)*"|[^,]*)', value):
        raw = match.group(2).strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        attributes[match.group(1)] = raw
    return attributes



def parse_hls_renditions(base_url: str, playlist: str) -> list[HLSRendition]:
    """Parse alternate AUDIO and SUBTITLES tracks from an HLS master playlist."""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be a valid HTTP(S) URL")
    lines = [line.strip() for line in playlist.lstrip("\ufeff").splitlines()]
    if not lines or lines[0] != "#EXTM3U":
        raise ValueError("Not a valid HLS playlist")

    renditions: list[HLSRendition] = []
    for line in lines:
        if not line.startswith("#EXT-X-MEDIA:"):
            continue
        attrs = _parse_attribute_list(line.partition(":")[2])
        kind = attrs.get("TYPE", "").upper()
        if kind not in {"AUDIO", "SUBTITLES"}:
            continue
        raw_url = attrs.get("URI")
        renditions.append(
            HLSRendition(
                kind=kind.lower(),
                group_id=attrs.get("GROUP-ID"),
                name=attrs.get("NAME"),
                language=attrs.get("LANGUAGE") or attrs.get("ASSOC-LANGUAGE"),
                url=urljoin(base_url, raw_url) if raw_url else None,
                is_default=attrs.get("DEFAULT", "NO").upper() == "YES",
                autoselect=attrs.get("AUTOSELECT", "NO").upper() == "YES",
                forced=attrs.get("FORCED", "NO").upper() == "YES",
            )
        )
    return renditions


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
                audio_group=pending.get("AUDIO"),
                subtitle_group=pending.get("SUBTITLES"),
            )
        )
        pending = None

    return variants
