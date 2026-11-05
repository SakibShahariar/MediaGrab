"""Optional site-specific media extractors loaded from trusted Python entry points.

Plugins receive only the candidate URL. They are not given browser cookies,
request headers, credentials, or a privileged network/session object.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Iterable, Protocol

from mediagrab.url_utils import is_valid_http_url

_LOG = logging.getLogger("mediagrab.extractors")
ENTRY_POINT_GROUP = "mediagrab.extractors"
CAPABILITY_CANDIDATE_EXPANSION = "candidate-expansion"
MAX_CONCURRENT_EXTRACTOR_RUNS = 2
MAX_CANDIDATES_PER_PLUGIN = 50
MAX_CANDIDATES_TOTAL = 100
_WORKER_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_EXTRACTOR_RUNS)


def reserve_extractor_worker() -> bool:
    """Reserve one of the bounded background slots without blocking the UI."""
    return _WORKER_SLOTS.acquire(blocking=False)


def release_extractor_worker() -> None:
    """Release a background slot after plugin discovery completes."""
    _WORKER_SLOTS.release()


@dataclass(frozen=True)
class ExtractedMedia:
    """A site extractor's additional candidate, not an approved download."""

    url: str
    title: str | None = None
    media_type: str | None = None


class SiteExtractor(Protocol):
    """Minimal plugin contract. Implementations must declare capabilities."""

    name: str
    capabilities: frozenset[str]

    def supports(self, url: str) -> bool: ...

    def extract(self, url: str) -> Iterable[ExtractedMedia]: ...


def _load_extractor(entry_point):
    loaded = entry_point.load()
    if isinstance(loaded, type):
        loaded = loaded()
    elif callable(loaded) and not hasattr(loaded, "extract"):
        loaded = loaded()
    return loaded


def discover_media_candidates(url: str) -> list[ExtractedMedia]:
    """Ask installed candidate-expansion plugins for additional HTTP(S) URLs.

    A broken, unsupported, or malformed plugin is skipped independently.
    Returned candidates are validated and de-duplicated; no download is started.
    """
    if not is_valid_http_url(url):
        return []
    try:
        plugins = entry_points(group=ENTRY_POINT_GROUP)
    except Exception as exc:
        _LOG.warning("Could not discover site extractors (%s)", type(exc).__name__)
        return []

    candidates: list[ExtractedMedia] = []
    seen = {url}
    for entry_point in plugins:
        plugin_name = getattr(entry_point, "name", "unknown")
        try:
            plugin = _load_extractor(entry_point)
            capabilities = getattr(plugin, "capabilities", ())
            if CAPABILITY_CANDIDATE_EXPANSION not in capabilities:
                continue
            supports = getattr(plugin, "supports", None)
            extract = getattr(plugin, "extract", None)
            if not callable(supports) or not callable(extract) or not supports(url):
                continue
            extracted = extract(url)
            if extracted is None:
                continue
            plugin_count = 0
            for item in extracted:
                if plugin_count >= MAX_CANDIDATES_PER_PLUGIN or len(candidates) >= MAX_CANDIDATES_TOTAL:
                    break
                if not isinstance(item, ExtractedMedia):
                    continue
                candidate_url = item.url.strip() if isinstance(item.url, str) else ""
                if not is_valid_http_url(candidate_url) or candidate_url in seen:
                    continue
                seen.add(candidate_url)
                title = item.title.strip() if isinstance(item.title, str) and item.title.strip() else None
                media_type = item.media_type.strip() if isinstance(item.media_type, str) and item.media_type.strip() else None
                candidates.append(ExtractedMedia(candidate_url, title, media_type))
                plugin_count += 1
        except Exception as exc:
            # Plugins are optional. Do not let one failure interrupt core capture
            # or expose exception text that may contain signed URLs.
            _LOG.warning(
                "Site extractor %s failed (%s)",
                plugin_name,
                type(exc).__name__,
            )
    return candidates
