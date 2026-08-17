from __future__ import annotations

from urllib.parse import urlparse


def valid_playback_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False
