import secrets
import time
from typing import Optional

_HTML_CACHE: dict[str, tuple[float, str]] = {}
_TTL_SECONDS = 60 * 10


def _purge_expired(now: float) -> None:
    expired = [key for key, (ts, _) in _HTML_CACHE.items() if now - ts > _TTL_SECONDS]
    for key in expired:
        _HTML_CACHE.pop(key, None)


def store_html(html: str) -> str:
    """Store HTML and return a short-lived token."""
    now = time.time()
    _purge_expired(now)
    token = secrets.token_urlsafe(16)
    _HTML_CACHE[token] = (now, html)
    return token


def take_html(token: str) -> Optional[str]:
    """Retrieve and remove HTML by token."""
    if not token:
        return None
    entry = _HTML_CACHE.pop(token, None)
    if not entry:
        return None
    _, html = entry
    return html


def get_html(token: str) -> Optional[str]:
    """Retrieve HTML by token without removing it."""
    if not token:
        return None
    entry = _HTML_CACHE.get(token)
    if not entry:
        return None
    _, html = entry
    return html
