"""Canvas-first Pylogue app: 2D card surface + chat control plane."""

from __future__ import annotations

from pathlib import Path

from fasthtml.common import *
from monsterui.all import Button, ButtonT, FastHTML as MUFastHTML
from starlette.responses import FileResponse

from pylogue.core import (
    EchoResponder,
    get_core_headers,
    register_core_static,
    register_ws_routes,
    render_cards,
    render_input,
)

_CORE_STATIC_DIR = Path(__file__).resolve().parent / "static"

CANVAS_ACTION_INSTRUCTIONS = """
You are connected to a 2D card canvas. When the user asks to create/update/delete cards or card content, emit one fenced block exactly in this format:

```pylogue-canvas
{"actions": [ ... ]}
```

Supported actions:
- create_card: {"op":"create_card","card":{"id?":str,"title?":str,"x?":number,"y?":number,"w?":number,"h?":number,"content?":[]}}
- update_card: {"op":"update_card","id":str,"patch":{...}}
- delete_card: {"op":"delete_card","id":str}
- create_content: {"op":"create_content","card_id":str,"content":{"id?":str,"type?":"text|html","text?":str,"html?":str,"align?":"left|center|right"}}
- update_content: {"op":"update_content","card_id":str,"content_id":str,"patch":{...}}
- delete_content: {"op":"delete_content","card_id":str,"content_id":str}

Rules:
- Keep normal assistant text concise.
- Only include valid JSON in the fenced block.
- Prefer patching existing cards/content over recreating unless user requests replacement.
- If the `canvas_actions` tool is available, call it with `actions=[...]` for every canvas mutation.
- Tool call is the source of truth for execution; fenced block is optional fallback.
""".strip()


def _with_canvas_instructions(responder):
    if responder is not None and hasattr(responder, "append_instructions"):
        try:
            responder.append_instructions(CANVAS_ACTION_INSTRUCTIONS)
        except Exception:
            pass
    return responder


def app_factory(
    responder=None,
    responder_factory=None,
    title: str = "Pylogue Canvas Alpha",
    subtitle: str = "2D cards are layouted on canvas; chat controls card/content CRUD via typed actions.",
) -> MUFastHTML:
    if responder_factory is None:
        responder = _with_canvas_instructions(responder or EchoResponder())
    else:
        source_factory = responder_factory

        def _factory():
            return _with_canvas_instructions(source_factory())

        responder_factory = _factory

    headers = list(get_core_headers(include_markdown=True))
    headers.extend(
        [
            Link(
                rel="stylesheet",
                href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap",
            ),
            Link(rel="stylesheet", href="/static/pylogue-canvas.css"),
            Script(src="/static/pylogue-canvas.js", type="module"),
        ]
    )
    app = MUFastHTML(exts="ws", hdrs=tuple(headers), pico=False)
    register_core_static(app)

    @app.route("/static/pylogue-canvas.css")
    def _canvas_css():
        return FileResponse(_CORE_STATIC_DIR / "pylogue-canvas.css")

    @app.route("/static/pylogue-canvas.js")
    def _canvas_js():
        return FileResponse(_CORE_STATIC_DIR / "pylogue-canvas.js")

    register_ws_routes(
        app,
        responder=responder,
        responder_factory=responder_factory,
    )

    def _chat_panel():
        return Div(
            Div(
                H2("Chat", cls="canvas-chat-title"),
                P("Use natural language. Assistant emits `pylogue-canvas` actions.", cls="canvas-chat-subtitle"),
                cls="canvas-chat-head",
            ),
            Div(render_cards([]), cls="canvas-chat-cards-wrap"),
            Form(
                render_input(),
                Div(
                    Button("Send", cls=ButtonT.primary, type="submit", id="chat-send-btn"),
                    Button("New Card", type="button", id="canvas-add-card-btn", cls=ButtonT.secondary),
                    cls="canvas-chat-actions",
                ),
                Input(type="hidden", id="canvas-state", name="canvas-state", value="{}"),
                id="form",
                hx_ext="ws",
                ws_connect="/ws",
                ws_send=True,
                hx_target="#cards",
                hx_swap="outerHTML",
                cls="canvas-chat-form",
            ),
            cls="canvas-chat-panel",
        )

    def _canvas_panel():
        return Div(
            Div(
                Div(
                    H1(title, cls="canvas-page-title"),
                    P(subtitle, cls="canvas-page-subtitle"),
                    cls="canvas-hero-copy",
                ),
                Div(
                    Span("Drag headers to move, drag corner to resize."),
                    cls="canvas-hero-hint",
                ),
                cls="canvas-hero",
            ),
            Div(id="pylogue-canvas-root", cls="pylogue-canvas-root"),
            cls="canvas-main-panel",
        )

    @app.route("/")
    def home():
        return (
            Title(title),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(
                Div(
                    _canvas_panel(),
                    _chat_panel(),
                    cls="canvas-app-shell",
                ),
                cls="canvas-page-body",
            ),
        )

    return app


def main(
    responder=None,
    responder_factory=None,
    title: str = "Pylogue Canvas Alpha",
    subtitle: str = "2D cards are layouted on canvas; chat controls card/content CRUD via typed actions.",
):
    if responder is None and responder_factory is None:
        responder = EchoResponder()

    if responder_factory is None and responder is not None and hasattr(responder, "message_history"):
        raise ValueError(
            "Responder appears stateful (has message_history). Pass responder_factory instead."
        )

    def _factory():
        return app_factory(
            responder=responder,
            responder_factory=responder_factory,
            title=title,
            subtitle=subtitle,
        )

    return _factory()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "pylogue.canvas:main",
        host="0.0.0.0",
        port=5012,
        reload=True,
        factory=True,
    )
