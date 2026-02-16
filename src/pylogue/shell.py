"""
Chat app wrapper with multiple local histories.
Run: python -m scripts.examples.chat_app_with_histories.main
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
from uuid import uuid4

from fasthtml.common import *
from fastsql import Database
from monsterui.all import (
    Button,
    ButtonT,
    Container,
    ContainerT,
    FastHTML as MUFastHTML,
    TextPresets,
    Theme,
    UkIcon,
)

from pylogue.core import (
    EchoResponder,
    IMPORT_PREFIX,
    _register_google_auth_routes,
    _session_cookie_name,
    google_oauth_config_from_env,
    get_core_headers,
    register_core_static,
    register_ws_routes,
    render_cards,
    render_input,
)
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.responses import JSONResponse
from starlette.responses import RedirectResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAT_APP_DIR = PROJECT_ROOT / "scripts" / "examples" / "chat_app_with_histories"
STATIC_DIR = Path(__file__).resolve().parent / "static"
DB_PATH = CHAT_APP_DIR / "chat_app.db"


@dataclass
class Chat:
    id: str
    title: str
    created_at: str
    updated_at: str
    payload: str = ""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def app_factory(
    responder=None,
    responder_factory=None,
    db_path: Path | str | None = None,
    sidebar_title: str = "Pylogue",
    hero_title: str = "Fast HTML + Pylogue Core",
    hero_subtitle: str = (
        "One UI wraps multiple Pylogue chat sessions. Pick a chat on the left, "
        "start a new one, or return to previous conversations instantly."
    ),
) -> MUFastHTML:
    if db_path is None:
        caller_frame = inspect.stack()[1]
        caller_file = Path(caller_frame.filename).resolve()
        caller_name = caller_file.stem
        resolved_db_path = caller_file.parent / f"{caller_name}.db"
    else:
        resolved_db_path = Path(db_path)
    local_db = Database(f"sqlite:///{resolved_db_path}")
    if responder_factory is None:
        responder = responder or EchoResponder()
    headers = list(get_core_headers(include_markdown=True))
    headers.extend(
        [
            Link(
                rel="stylesheet",
                href="https://fonts.googleapis.com/css2?family=Martel+Sans:wght@300;400;500;600;700&display=swap",
            ),
            Link(rel="stylesheet", href="/static/chat_app.css"),
            Script(src="/static/chat_app.js", type="module"),
        ]
    )

    oauth_cfg = google_oauth_config_from_env()
    auth_required = bool(oauth_cfg and oauth_cfg.auth_required)
    session_secret = (
        oauth_cfg.session_secret
        if oauth_cfg and oauth_cfg.session_secret
        else os.getenv("PYLOGUE_SESSION_SECRET")
    )
    app_kwargs = {"exts": "ws", "hdrs": tuple(headers), "pico": False}
    app_kwargs["session_cookie"] = _session_cookie_name()
    if session_secret:
        app_kwargs["secret_key"] = session_secret
    app = MUFastHTML(**app_kwargs)
    register_core_static(app)
    auth_paths = _register_google_auth_routes(app, oauth_cfg) if oauth_cfg else None

    def _is_authorized(request: Request) -> bool:
        if not auth_required:
            return True
        auth = request.session.get("auth")
        return isinstance(auth, dict)

    @app.route("/static/chat_app.css")
    def _chat_app_css():
        return FileResponse(STATIC_DIR / "chat_app.css")

    @app.route("/static/chat_app.js")
    def _chat_app_js():
        return FileResponse(STATIC_DIR / "chat_app.js")

    @app.route("/api/chats", methods=["GET"])
    def list_chats(request: Request):
        if not _is_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        items = list(local_db.create(Chat, pk="id")())
        items.sort(key=lambda c: c.updated_at or c.created_at, reverse=True)
        return JSONResponse(
            [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                }
                for c in items
            ]
        )

    @app.route("/api/chats", methods=["POST"])
    async def create_chat(request: Request):
        if not _is_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        chats = local_db.create(Chat, pk="id")
        data = await request.json()
        chat_id = data.get("id") or str(uuid4())
        title = data.get("title") or "New chat"
        now = _utc_iso()
        payload = data.get("payload")
        payload_str = json.dumps(payload) if payload is not None else ""
        chat = Chat(chat_id, title, now, now, payload_str)
        try:
            _ = chats[chat_id]
            chats.update(chat)
        except Exception:
            chats.insert(chat)
        return JSONResponse(
            {
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
            }
        )

    @app.route("/api/chats/{chat_id}", methods=["GET"])
    def get_chat(request: Request, chat_id: str):
        if not _is_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        chats = local_db.create(Chat, pk="id")
        try:
            chat = chats[chat_id]
        except Exception:
            return JSONResponse({"cards": []})
        payload = chat.payload or ""
        if not payload:
            return JSONResponse({"cards": []})
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"cards": []}
        return JSONResponse(data)

    @app.route("/api/chats/{chat_id}", methods=["POST"])
    async def save_chat(chat_id: str, request: Request):
        if not _is_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        chats = local_db.create(Chat, pk="id")
        data = await request.json()
        payload = data.get("payload") or {"cards": []}
        title = data.get("title") or "New chat"
        now = _utc_iso()
        try:
            existing = chats[chat_id]
            created_at = existing.created_at
        except Exception:
            created_at = data.get("created_at") or now
        chat = Chat(chat_id, title, created_at, now, json.dumps(payload))
        try:
            _ = chats[chat_id]
            chats.update(chat)
        except Exception:
            chats.insert(chat)
        return JSONResponse(
            {
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
            }
        )

    @app.route("/api/chats/{chat_id}", methods=["DELETE"])
    def delete_chat(request: Request, chat_id: str):
        if not _is_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        chats = local_db.create(Chat, pk="id")
        try:
            chats.delete(chat_id)
        except Exception:
            pass
        return JSONResponse({"deleted": True})

    sessions: dict[int, dict] = {}
    register_ws_routes(
        app,
        responder=responder,
        responder_factory=responder_factory,
        sessions=sessions,
        auth_required=auth_required,
    )

    def _sidebar(request: Request):
        show_logout = auth_required and _is_authorized(request)
        logout_href = auth_paths["logout_path"] if auth_paths else "/logout"
        return Div(
            Div(
                H1(sidebar_title, cls="text-xl font-semibold"),
                Div(
                    Button(
                        "Close",
                        type="button",
                        id="close-sidebar-btn",
                        cls=(ButtonT.secondary, "text-xs mobile-only-inline"),
                    ),
                    A(
                        UkIcon("sign-out"),
                        Span("Logout"),
                        href=logout_href,
                        cls=(ButtonT.secondary, "text-xs"),
                    ) if show_logout else None,
                    cls="flex items-center gap-2",
                ),
                cls="sidebar-header",
            ),
            Button(
                # UkIcon("plus"),
                Span("New chat"),
                cls=(ButtonT.secondary, "w-full justify-center"),
                type="button",
                id="new-chat-btn",
            ),
            Div(id="chat-list", cls="chat-list"),
            cls="sidebar",
        )

    def _hero():
        return Div(
            Div(
                H2(hero_title, cls="hero-title"),
                P(hero_subtitle, cls="hero-sub"),
                cls="space-y-2",
            ),
            Div(
                Button(
                    "Chats",
                    type="button",
                    id="sidebar-toggle-btn",
                    cls=(ButtonT.secondary, "mobile-only-inline"),
                ),
                Button(
                    UkIcon("download"),
                    cls="uk-button uk-button-text copy-chat-btn",
                    type="button",
                    aria_label="Download conversation JSON",
                    title="Download conversation JSON",
                ),
                Button(
                    UkIcon("upload"),
                    cls="uk-button uk-button-text copy-chat-btn upload-chat-btn",
                    type="button",
                    aria_label="Upload conversation JSON",
                    title="Upload conversation JSON",
                ),
                Input(
                    type="file",
                    id="chat-upload",
                    accept="application/json",
                    cls="sr-only",
                ),
                cls="flex gap-2 justify-end",
            ),
            cls="hero",
        )

    def _chat_content():
        return Div(
            render_cards([]),
            cls="chat-content-wrapper",
        )

    def _chat_input():
        return Div(
            Form(
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
                cls="flex flex-col sm:flex-row gap-3 items-stretch",
            ),
            cls="chat-input-area",
        )

    def _main_panel():
        return Div(
            _hero(),
            _chat_content(),
            _chat_input(),
            cls="main-panel",
        )

    def _delete_chat_modal():
        return Div(
            Div(
                H3("Delete chat?", cls="delete-chat-modal-title"),
                P(
                    "This will permanently delete ",
                    Strong("", id="delete-chat-name"),
                    ".",
                    cls="delete-chat-modal-text",
                ),
                Div(
                    Button(
                        "Cancel",
                        type="button",
                        id="delete-chat-cancel-btn",
                        cls=(ButtonT.secondary, "delete-chat-cancel-btn"),
                    ),
                    Button(
                        "Delete",
                        type="button",
                        id="delete-chat-confirm-btn",
                        cls=(ButtonT.primary, "delete-chat-confirm-btn"),
                    ),
                    cls="delete-chat-modal-actions",
                ),
                cls="delete-chat-modal-card",
            ),
            id="delete-chat-modal",
            cls="delete-chat-modal",
            aria_hidden="true",
            role="dialog",
            aria_modal="true",
            tabindex="-1",
        )
    
    def _shell(request: Request):
        return Div(
            Div(id="sidebar-backdrop", cls="sidebar-backdrop"),
            _sidebar(request),
            _main_panel(),
            _delete_chat_modal(),
            cls="app-shell",
        )

    @app.route("/")
    def home(request: Request):
        if auth_required and not _is_authorized(request):
            request.session["next"] = "/"
            login_path = auth_paths["login_path"] if auth_paths else "/login"
            return RedirectResponse(login_path, status_code=303)
        return (
            Title(hero_title),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(
                _shell(request),
                cls="min-h-screen",
                data_import_prefix=IMPORT_PREFIX,
            ),
        )

    return app
