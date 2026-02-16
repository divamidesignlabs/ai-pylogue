from fasthtml.common import Body, Div, Form, H2, Link, Meta, Script, Title
from monsterui.all import Button, ButtonT, FastHTML as MUFastHTML
import asyncio
import logging
import os
from pathlib import Path
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
    CANVAS_STORE,
    subscribe_canvas,
    unsubscribe_canvas,
)

CANVAS_STATIC_DIR = Path(__file__).resolve().parent / "static"
_LOG = logging.getLogger(__name__)


def _canvas_panel(canvas_items, oob: bool = False):
    attrs = {}
    if oob:
        attrs["hx_swap_oob"] = "outerHTML"
    return Div(
        H2("Canvas", cls="text-lg font-semibold text-slate-700 mb-3"),
        Div(render_canvas(canvas_items), id="canvas-root", cls="canvas-empty canvas-root"),
        cls="canvas-left",
        id="canvas-panel",
        hx_get="/canvas/panel",
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


def _layout_shell(canvas_items):
    return Div(
        _canvas_panel(canvas_items),
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
    def home():
        canvas_items = CANVAS_STORE.list_items()
        return (
            Title("Pylogue Canvas MVP"),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(_layout_shell(canvas_items)),
        )

    @app.route("/canvas/panel")
    def canvas_panel():
        items = CANVAS_STORE.list_items()
        _LOG.info("Canvas panel render requested: items=%s", len(items))
        return _canvas_panel(items)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("canvas.main:main", host="0.0.0.0", port=5004, reload=True, factory=True)
