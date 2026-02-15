from fasthtml.common import Body, Div, Form, H2, Link, Meta, Title
from monsterui.all import Button, ButtonT, FastHTML as MUFastHTML
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
from canvas.crud import CanvasItemCRUD
from canvas.data import CANVAS_ITEMS

CANVAS_STATIC_DIR = Path(__file__).resolve().parent / "static"
CANVAS_STORE = CanvasItemCRUD(CANVAS_ITEMS)


def _canvas_panel(canvas_items):
    return Div(
        H2("Canvas", cls="text-lg font-semibold text-slate-700 mb-3"),
        Div(render_canvas(canvas_items), id="canvas-root", cls="canvas-empty canvas-root"),
        cls="canvas-left",
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

    app_kwargs = {"exts": "ws", "hdrs": tuple(headers), "pico": False}
    app_kwargs["session_cookie"] = _session_cookie_name()
    session_secret = os.getenv("PYLOGUE_SESSION_SECRET")
    if session_secret:
        app_kwargs["secret_key"] = session_secret

    app = MUFastHTML(**app_kwargs)
    register_core_static(app)
    register_ws_routes(app, responder=responder, responder_factory=responder_factory)

    @app.route("/static/canvas.css")
    def _canvas_css():
        return FileResponse(CANVAS_STATIC_DIR / "canvas.css")

    @app.route("/")
    def home():
        canvas_items = CANVAS_STORE.list_items()
        return (
            Title("Pylogue Canvas MVP"),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(_layout_shell(canvas_items)),
        )

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("canvas.main:main", host="0.0.0.0", port=5004, reload=True, factory=True)
