from fasthtml.common import A, Body, Div, Form, H2, Link, Meta, Script, Title
from monsterui.all import Button, ButtonT, FastHTML as MUFastHTML
import asyncio
import logging
import os
from pathlib import Path
from starlette.requests import Request
from starlette.responses import FileResponse

from pylogue.core import (
    EchoResponder,
    _session_cookie_name,
    get_core_headers,
    register_core_static,
    register_ws_routes,
    render_cards,
    render_input,
)
from canvas.components import render_canvas
from canvas.state import (
    get_canvas_store,
    subscribe_canvas,
    unsubscribe_canvas,
)

CANVAS_STATIC_DIR = Path(__file__).resolve().parent / "static"
_LOG = logging.getLogger(__name__)


def _canvas_breadcrumbs(canvas_id: str, parent_canvas_id: str | None = None):
    current = canvas_id.strip() or "main"
    if current == "main":
        return Div(
            A("Main", href="/canvas/main", cls="text-sm font-semibold text-slate-700"),
            cls="flex items-center gap-2",
        )
    parent = (parent_canvas_id or "main").strip() or "main"
    if parent == "main":
        return Div(
            A("Main", href="/canvas/main", cls="text-sm text-slate-600 hover:text-slate-900"),
            Div("/", cls="text-slate-400"),
            Div(current, cls="text-sm font-semibold text-slate-700"),
            cls="flex items-center gap-2",
        )
    return Div(
        A("Main", href="/canvas/main", cls="text-sm text-slate-600 hover:text-slate-900"),
        Div("/", cls="text-slate-400"),
        A(parent, href=f"/canvas/{parent}", cls="text-sm text-slate-600 hover:text-slate-900"),
        Div("/", cls="text-slate-400"),
        Div(current, cls="text-sm font-semibold text-slate-700"),
        cls="flex items-center gap-2",
    )


def _canvas_panel(canvas_id: str, canvas_items, parent_canvas_id: str | None = None, oob: bool = False):
    attrs = {}
    if oob:
        attrs["hx_swap_oob"] = "outerHTML"
    panel_href = f"/canvas/{canvas_id}/panel"
    if parent_canvas_id:
        panel_href = f"{panel_href}?from={parent_canvas_id}"
    return Div(
        Div(
            H2("Canvas", cls="text-lg font-semibold text-slate-700"),
            _canvas_breadcrumbs(canvas_id, parent_canvas_id=parent_canvas_id),
            cls="flex items-center justify-between mb-3",
        ),
        Div(render_canvas(canvas_items, current_canvas_id=canvas_id), id="canvas-root", cls="canvas-empty canvas-root"),
        cls="canvas-left",
        id="canvas-panel",
        hx_get=panel_href,
        hx_trigger="canvas_refresh from:body",
        hx_swap="outerHTML",
        **attrs,
    )


def _chat_form():
    return Form(
        render_input(),
        Div(
            Button("Send", cls=ButtonT.primary, type="submit", id="chat-send-btn"),
            cls="flex items-center",
        ),
        id="form",
        hx_ext="ws",
        ws_connect="/ws",
        ws_send=True,
        hx_target="#cards",
        hx_swap="outerHTML",
        cls="flex flex-col sm:flex-row gap-3 items-stretch pt-4",
    )


def _chat_panel():
    return Div(
        H2("Chat", cls="text-lg font-semibold text-slate-700 mb-3"),
        Div(
            render_cards([]),
            _chat_form(),
            cls="space-y-4 canvas-chat-body",
        ),
        cls="canvas-right",
    )


def _layout_shell(canvas_id: str, canvas_items, parent_canvas_id: str | None = None):
    return Div(
        _canvas_panel(canvas_id, canvas_items, parent_canvas_id=parent_canvas_id),
        _chat_panel(),
        cls="canvas-shell",
    )


def main(responder=None, responder_factory=None):
    """Canvas MVP: left blank canvas, right Pylogue chat."""
    if responder_factory is None:
        responder = responder or EchoResponder()

    headers = list(get_core_headers(include_markdown=True))
    headers.append(Link(rel="stylesheet", href="/static/canvas.css"))
    headers.append(Script(src="/static/canvas-ws.js", type="module"))

    app_kwargs = {"exts": "ws", "hdrs": tuple(headers), "pico": False}
    app_kwargs["session_cookie"] = _session_cookie_name()
    session_secret = os.getenv("PYLOGUE_SESSION_SECRET")
    if session_secret:
        app_kwargs["secret_key"] = session_secret

    app = MUFastHTML(**app_kwargs)
    register_core_static(app)
    register_ws_routes(app, responder=responder, responder_factory=responder_factory)

    canvas_ws_sessions: dict[int, int] = {}

    async def _on_canvas_ws_connect(ws, send):
        token = subscribe_canvas(send, loop=asyncio.get_running_loop())
        canvas_ws_sessions[id(ws)] = token
        return "canvas_refresh"

    def _on_canvas_ws_disconnect(ws):
        token = canvas_ws_sessions.pop(id(ws), None)
        if token is not None:
            unsubscribe_canvas(token)

    @app.ws("/canvas/ws", conn=_on_canvas_ws_connect, disconn=_on_canvas_ws_disconnect)
    async def _canvas_ws(_msg: str, send, ws):
        return

    @app.route("/static/canvas.css")
    def _canvas_css():
        return FileResponse(CANVAS_STATIC_DIR / "canvas.css")

    @app.route("/static/canvas-ws.js")
    def _canvas_ws_js():
        return FileResponse(CANVAS_STATIC_DIR / "canvas-ws.js")

    @app.route("/")
    def home(request: Request):
        return canvas_home(request, "main")

    @app.route("/canvas/{canvas_id}")
    def canvas_home(request: Request, canvas_id: str):
        request.session["canvas_current_id"] = canvas_id
        store = get_canvas_store(canvas_id)
        canvas_items = store.list_items()
        parent_canvas_id = request.query_params.get("from")
        return (
            Title(f"Pylogue Canvas MVP - {canvas_id}"),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(_layout_shell(canvas_id, canvas_items, parent_canvas_id=parent_canvas_id)),
        )

    @app.route("/canvas/{canvas_id}/panel")
    def canvas_panel(request: Request, canvas_id: str):
        items = get_canvas_store(canvas_id).list_items()
        parent_canvas_id = request.query_params.get("from")
        _LOG.info("Canvas panel render requested: items=%s", len(items))
        return _canvas_panel(canvas_id, items, parent_canvas_id=parent_canvas_id)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("canvas.main:main", host="0.0.0.0", port=5004, reload=True, factory=True)
