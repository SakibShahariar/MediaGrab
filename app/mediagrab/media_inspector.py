"""Fetch and inspect HLS/DASH manifests for available media choices.

This module reads bounded manifest responses only. It does not fetch media segments,
collect browser cookies, or bypass access controls.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from mediagrab.capture import (
    DASHRepresentation,
    HLSRendition,
    HLSVariant,
    MediaKind,
    classify_media,
    parse_dash_representations,
    parse_hls_master_playlist,
    parse_hls_renditions,
)

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT = 12.0


@dataclass(frozen=True)
class ManifestInspection:
    url: str
    kind: MediaKind
    content_type: str
    variants: tuple[HLSVariant, ...] = ()
    renditions: tuple[HLSRendition, ...] = ()
    representations: tuple[DASHRepresentation, ...] = ()


def inspect_manifest(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> ManifestInspection:
    """Fetch a bounded HTTP(S) manifest and parse available choices."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only valid HTTP(S) manifest URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs with embedded credentials are not accepted")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    request = Request(url, headers={"User-Agent": "MediaGrab/0.1", "Accept": "*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            final = urlparse(final_url)
            if final.scheme not in {"http", "https"} or not final.hostname:
                raise ValueError("Manifest redirected to an unsupported URL")
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_MANIFEST_BYTES + 1)
    except HTTPError as exc:
        raise ValueError(f"Manifest request failed with HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"Could not fetch manifest ({type(exc).__name__})") from exc

    if len(body) > MAX_MANIFEST_BYTES:
        raise ValueError(f"Manifest exceeds the {MAX_MANIFEST_BYTES}-byte size limit")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Manifest is not valid UTF-8 text") from exc

    kind = classify_media(final_url, content_type)
    if kind is MediaKind.HLS:
        variants = tuple(parse_hls_master_playlist(final_url, text))
        renditions = tuple(parse_hls_renditions(final_url, text))
        return ManifestInspection(final_url, kind, content_type, variants, renditions)
    if kind is MediaKind.DASH:
        reps = tuple(parse_dash_representations(final_url, text))
        return ManifestInspection(final_url, kind, content_type, representations=reps)
    raise ValueError("URL did not return a recognizable HLS or DASH manifest")


def _safe_url_label(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc + parsed.path


def _format_bandwidth(value: int | None) -> str:
    return f"{value / 1000:.0f} kb/s" if value else "unknown bitrate"


def format_inspection(result: ManifestInspection) -> str:
    """Format choices without exposing URL query strings or fragments."""
    lines = [f"Manifest: {_safe_url_label(result.url)}", f"Type: {result.kind.value.upper()}"]
    if result.kind is MediaKind.HLS:
        if result.variants:
            lines.append("Video variants:")
            for index, item in enumerate(sorted(result.variants, key=lambda v: (v.height or 0, v.bandwidth or 0)), 1):
                resolution = f"{item.width}x{item.height}" if item.width and item.height else "resolution unknown"
                lines.append(f"  {index}. {resolution}, {_format_bandwidth(item.bandwidth)}")
        else:
            lines.append("Video variants: none (this may be a media playlist rather than a master playlist)")
        if result.renditions:
            lines.append("Alternate tracks:")
            for item in result.renditions:
                label = item.name or item.language or "unnamed track"
                language = f", language {item.language}" if item.language else ""
                flags = ", default" if item.is_default else ""
                flags += ", forced" if item.forced else ""
                lines.append(f"  - {item.kind}: {label}{language}{flags}")
        else:
            lines.append("Alternate tracks: none declared")
    else:
        if not result.representations:
            lines.append("DASH representations: none found")
        else:
            lines.append("DASH representations:")
            for index, item in enumerate(sorted(result.representations, key=lambda r: (r.height or 0, r.bandwidth or 0)), 1):
                resolution = f"{item.width}x{item.height}" if item.width and item.height else "resolution unknown"
                media_type = item.mime_type or "type unknown"
                lines.append(f"  {index}. {resolution}, {_format_bandwidth(item.bandwidth)}, {media_type}")
    lines.append("Note: this reports declared manifest metadata; it does not guarantee every choice is playable.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect HLS/DASH quality and alternate-track metadata.")
    parser.add_argument("url", help="HTTP(S) HLS .m3u8 or DASH .mpd manifest URL")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="network timeout in seconds (default: 12)")
    args = parser.parse_args(argv)
    try:
        result = inspect_manifest(args.url, timeout=args.timeout)
    except ValueError as exc:
        print(f"MediaGrab inspector: {exc}", file=sys.stderr)
        return 2
    print(format_inspection(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
