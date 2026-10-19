"""URL display helpers that avoid exposing signed query values in the UI."""

from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    """Hide query and fragment values while preserving a useful URL preview."""
    parsed = urlsplit(url)
    query = "…" if parsed.query else ""
    fragment = "…" if parsed.fragment else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, fragment))
