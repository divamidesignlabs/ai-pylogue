import asyncio
import logging
from typing import Awaitable, Callable

from canvas.crud import CanvasItemCRUD
from canvas.data import CANVAS_ITEMS

_LOG = logging.getLogger(__name__)
_CANVAS_SUBSCRIBERS: dict[int, Callable[[str], Awaitable[None]]] = {}
_CANVAS_LOOP: asyncio.AbstractEventLoop | None = None


def _resolve_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.get_event_loop_policy().get_event_loop()
        except Exception:
            return None


def subscribe_canvas(
    send: Callable[[str], Awaitable[None]],
    loop: asyncio.AbstractEventLoop | None = None,
) -> int:
    global _CANVAS_LOOP
    token = id(send)
    _CANVAS_SUBSCRIBERS[token] = send
    loop = loop or _resolve_loop()
    if loop is not None:
        _CANVAS_LOOP = loop
    _LOG.info("Canvas WS subscriber connected: token=%s, subscribers=%s", token, len(_CANVAS_SUBSCRIBERS))
    return token


def unsubscribe_canvas(token: int) -> None:
    _CANVAS_SUBSCRIBERS.pop(token, None)
    _LOG.info("Canvas WS subscriber removed: token=%s, subscribers=%s", token, len(_CANVAS_SUBSCRIBERS))


def publish_canvas_refresh() -> None:
    if not _CANVAS_SUBSCRIBERS:
        _LOG.info("Canvas refresh skipped: no subscribers")
        return

    payload = "canvas_refresh"
    subs = list(_CANVAS_SUBSCRIBERS.values())
    loop = _CANVAS_LOOP or _resolve_loop()
    if loop is None or not loop.is_running():
        _LOG.warning("Canvas refresh dropped: no available event loop")
        return
    _LOG.info("Canvas refresh publish: subscribers=%s", len(subs))
    for send in subs:
        asyncio.run_coroutine_threadsafe(send(payload), loop)


CANVAS_STORE = CanvasItemCRUD(CANVAS_ITEMS, on_change=publish_canvas_refresh)
