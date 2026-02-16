import asyncio
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable

from canvas.crud import CanvasItemCRUD

_LOG = logging.getLogger(__name__)
_CANVAS_SUBSCRIBERS: dict[int, Callable[[str], Awaitable[None]]] = {}
_CANVAS_LOOP: asyncio.AbstractEventLoop | None = None
_STORE_PATH = Path(__file__).resolve().parents[2] / ".canvas_items.json"
_CANVAS_STORES: dict[str, CanvasItemCRUD] = {}


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
    loop = _CANVAS_LOOP or _resolve_loop()
    if loop is None or not loop.is_running():
        _LOG.warning("Canvas refresh dropped: no available event loop")
        return
    for send in list(_CANVAS_SUBSCRIBERS.values()):
        asyncio.run_coroutine_threadsafe(send("canvas_refresh"), loop)


def _load_collections(path: Path | None = None) -> dict[str, list[dict]]:
    store_path = path or _STORE_PATH
    if not store_path.exists():
        return {"main": []}
    try:
        raw = json.loads(store_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            canvases = raw.get("canvases")
            if isinstance(canvases, dict):
                return {k: v for k, v in canvases.items() if isinstance(v, list)}
    except Exception:
        _LOG.exception("Failed to load canvas store from %s", store_path)
    return {"main": []}


def _save_collections(path: Path | None = None) -> None:
    store_path = path or _STORE_PATH
    data = {"canvases": {canvas_id: store.list_items() for canvas_id, store in _CANVAS_STORES.items()}}
    try:
        store_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        _LOG.exception("Failed to persist canvas store to %s", store_path)


def _on_canvas_change() -> None:
    _save_collections()
    publish_canvas_refresh()


def _hydrate_collections(collections: dict[str, list[dict]]) -> None:
    for canvas_id, items in collections.items():
        existing = _CANVAS_STORES.get(canvas_id)
        if existing is None:
            _CANVAS_STORES[canvas_id] = CanvasItemCRUD(items, on_change=_on_canvas_change)
        else:
            existing.set_items(items)


def configure_canvas_store(path: str | Path) -> None:
    global _STORE_PATH
    _STORE_PATH = Path(path).expanduser().resolve()
    _hydrate_collections(_load_collections(_STORE_PATH))
    _LOG.info("Canvas store path configured: %s", _STORE_PATH)


def get_canvas_store(canvas_id: str) -> CanvasItemCRUD:
    canvas_id = (canvas_id or "main").strip() or "main"
    store = _CANVAS_STORES.get(canvas_id)
    if store is None:
        store = CanvasItemCRUD([], on_change=_on_canvas_change)
        _CANVAS_STORES[canvas_id] = store
    return store


def list_canvas_ids() -> list[str]:
    return sorted(_CANVAS_STORES.keys())


_hydrate_collections(_load_collections())
CANVAS_STORE = get_canvas_store("main")
