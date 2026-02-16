import asyncio
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable

from canvas.crud import CanvasItemCRUD
from canvas.data import CANVAS_ITEMS

_LOG = logging.getLogger(__name__)
_CANVAS_SUBSCRIBERS: dict[int, Callable[[str], Awaitable[None]]] = {}
_CANVAS_LOOP: asyncio.AbstractEventLoop | None = None
_STORE_PATH = Path(__file__).resolve().parents[2] / ".canvas_items.json"


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


def _load_items(path: Path | None = None) -> list[dict]:
    store_path = path or _STORE_PATH
    if not store_path.exists():
        return CANVAS_ITEMS
    try:
        raw = json.loads(store_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
    except Exception:
        _LOG.exception("Failed to load canvas store from %s", store_path)
    return CANVAS_ITEMS


def _save_items(items: list[dict], path: Path | None = None) -> None:
    store_path = path or _STORE_PATH
    try:
        store_path.write_text(
            json.dumps(items, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    except Exception:
        _LOG.exception("Failed to persist canvas store to %s", store_path)


def _on_canvas_change() -> None:
    _save_items(CANVAS_STORE.list_items())
    publish_canvas_refresh()


def configure_canvas_store(path: str | Path) -> None:
    global _STORE_PATH
    _STORE_PATH = Path(path).expanduser().resolve()
    CANVAS_STORE.set_items(_load_items(_STORE_PATH))
    _LOG.info("Canvas store path configured: %s", _STORE_PATH)


CANVAS_STORE = CanvasItemCRUD(_load_items(), on_change=_on_canvas_change)
