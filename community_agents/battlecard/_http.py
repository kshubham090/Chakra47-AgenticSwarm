from __future__ import annotations

import requests
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "DNT": "1",
}

_TIMEOUT = 12

# Phrases that indicate a bot-detection / block page — not real content.
_BLOCK_SIGNALS = frozenset([
    "your request has been blocked",
    "access denied",
    "403 forbidden",
    "enable javascript and cookies",
    "please enable cookies",
    "captcha",
    "ddos protection",
    "ray id",                   # Cloudflare challenge pages
    "checking your browser",
    "just a moment",            # Cloudflare "Just a moment..." page
    "attention required",       # Cloudflare Attention page
    "security check",
])


def _is_blocked(html: str) -> bool:
    """Detect bot-block / challenge pages from the first 2 KB of content."""
    sample = html[:2000].lower()
    return any(sig in sample for sig in _BLOCK_SIGNALS)


def fetch(url: str, timeout: int = _TIMEOUT) -> tuple[str | None, dict[str, str]]:
    """Fetch URL. Returns (html_text, response_headers) or (None, {}) on failure/block."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        if _is_blocked(html):
            logger.warning("http: bot-block detected for %s", url)
            return None, {}
        return html, dict(resp.headers)
    except Exception as exc:
        logger.debug("http: fetch failed for %s — %s", url, exc)
        return None, {}


def fetch_json(url: str, timeout: int = _TIMEOUT) -> dict | list | None:
    """Fetch JSON endpoint. Returns None on failure."""
    try:
        resp = requests.get(
            url,
            headers={**_HEADERS, "Accept": "application/json"},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug("http: json fetch failed for %s — %s", url, exc)
        return None
