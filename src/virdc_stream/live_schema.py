from __future__ import annotations

import re
from urllib.parse import urlparse


LIVE_URL_RE = re.compile(r"^/@([^/?#]+)/live/?$", re.IGNORECASE)


def parse_live_url(value: str) -> str:
    """Return a TikTok LIVE broadcaster unique_id from a URL or @handle."""
    raw = str(value).strip()
    if raw.startswith("@") and "/" not in raw:
        username = raw[1:]
    else:
        parsed = urlparse(raw)
        if parsed.hostname not in {"www.tiktok.com", "tiktok.com", "m.tiktok.com"}:
            raise ValueError("Expected a tiktok.com LIVE URL")
        match = LIVE_URL_RE.match(parsed.path)
        if not match:
            raise ValueError("Expected a TikTok LIVE URL ending in /@username/live")
        username = match.group(1)
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,50}", username):
        raise ValueError("TikTok username is invalid")
    return username


def live_stream_id(unique_id: str) -> str:
    return f"live:{unique_id.lower()}"
