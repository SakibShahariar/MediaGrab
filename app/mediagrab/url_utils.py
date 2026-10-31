"""URL display helpers that avoid exposing signed query values in the UI."""

from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    """Hide query and fragment values while preserving a useful URL preview."""
    parsed = urlsplit(url)
    query = "…" if parsed.query else ""
    fragment = "…" if parsed.fragment else ""
    # Userinfo can contain passwords too; keep only the authority after the last @.
    authority = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, authority, parsed.path, query, fragment))



def is_valid_http_url(value: object) -> bool:
    """Return whether value is a well-formed credential-free HTTP(S) URL."""
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )
