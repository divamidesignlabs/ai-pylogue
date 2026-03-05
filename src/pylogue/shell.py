"""
Chat app wrapper with multiple local histories.
Run: python -m scripts.examples.chat_app_with_histories.main
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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
    _register_simple_auth_routes,
    _session_cookie_name,
    google_oauth_config_from_env,
    get_core_headers,
    register_core_static,
    register_ws_routes,
    render_cards,
    render_input,
    simple_auth_config_from_env,
)
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.responses import JSONResponse
from starlette.responses import RedirectResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAT_APP_DIR = PROJECT_ROOT / "scripts" / "examples" / "chat_app_with_histories"
STATIC_DIR = Path(__file__).resolve().parent / "static"
DB_PATH = CHAT_APP_DIR / "chat_app.db"
_LOG = logging.getLogger(__name__)


@dataclass
class Chat:
    id: str
    title: str
    created_at: str
    updated_at: str
    user_id: str
    payload: str = ""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def app_factory(
    responder=None,
    responder_factory=None,
    db_path: Path | str | None = None,
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
    simple_cfg = simple_auth_config_from_env()
    if oauth_cfg and simple_cfg:
        raise ValueError("Configure either Google OAuth or simple auth, not both.")
    auth_required = bool((oauth_cfg and oauth_cfg.auth_required) or (simple_cfg and simple_cfg.auth_required))
    session_secret = (
        oauth_cfg.session_secret
        if oauth_cfg and oauth_cfg.session_secret
        else simple_cfg.session_secret
        if simple_cfg and simple_cfg.session_secret
        else os.getenv("PYLOGUE_SESSION_SECRET")
    )
    app_kwargs = {"exts": "ws", "hdrs": tuple(headers), "pico": False}
    app_kwargs["session_cookie"] = _session_cookie_name()
    if session_secret:
        app_kwargs["secret_key"] = session_secret
    app = MUFastHTML(**app_kwargs)
    register_core_static(app)
    auth_paths = (
        _register_google_auth_routes(app, oauth_cfg)
        if oauth_cfg
        else _register_simple_auth_routes(app, simple_cfg)
        if simple_cfg
        else None
    )

    def _is_authorized(request: Request) -> bool:
        if not auth_required:
            return True
        auth = request.session.get("auth")
        return isinstance(auth, dict)

    def _get_user_id(request: Request) -> str:
        """Get user identifier from session (email or username)."""
        if not auth_required:
            return "default_user"
        auth = request.session.get("auth")
        if isinstance(auth, dict):
            return auth.get("email") or auth.get("username") or "unknown"
        return "unknown"

    def _get_user_role(request: Request) -> str:
        """Get user role from session. Defaults to 'user'."""
        if not auth_required:
            return "user"
        auth = request.session.get("auth")
        if isinstance(auth, dict):
            return auth.get("role", "user")
        return "user"

    def _is_admin(request: Request) -> bool:
        """Check if the current user is an admin."""
        return _get_user_role(request) == "admin"


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
        
        user_id = _get_user_id(request)
        is_admin = _is_admin(request)
        
        items = list(local_db.create(Chat, pk="id")())
        
        # Filter: admins see all, users see only their own
        if not is_admin:
            items = [c for c in items if c.user_id == user_id]
        
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
        
        user_id = _get_user_id(request)
        chats = local_db.create(Chat, pk="id")
        data = await request.json()
        chat_id = data.get("id") or str(uuid4())
        title = data.get("title") or "New chat"
        now = _utc_iso()
        payload = data.get("payload")
        payload_str = json.dumps(payload) if payload is not None else ""
        chat = Chat(chat_id, title, now, now, user_id, payload_str)
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
        
        user_id = _get_user_id(request)
        is_admin = _is_admin(request)
        
        chats = local_db.create(Chat, pk="id")
        try:
            chat = chats[chat_id]
            # Check ownership: user can only access their own, admin can access all
            if not is_admin and chat.user_id != user_id:
                return JSONResponse({"error": "Forbidden"}, status_code=403)
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
        
        user_id = _get_user_id(request)
        is_admin = _is_admin(request)
        
        chats = local_db.create(Chat, pk="id")
        data = await request.json()
        payload = data.get("payload") or {"cards": []}
        title = data.get("title") or "New chat"
        now = _utc_iso()
        try:
            existing = chats[chat_id]
            # Check ownership before updating
            if not is_admin and existing.user_id != user_id:
                return JSONResponse({"error": "Forbidden"}, status_code=403)
            created_at = existing.created_at
            owner_id = existing.user_id
        except Exception:
            created_at = data.get("created_at") or now
            owner_id = user_id
        
        chat = Chat(chat_id, title, created_at, now, owner_id, json.dumps(payload))
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
        
        user_id = _get_user_id(request)
        is_admin = _is_admin(request)
        
        chats = local_db.create(Chat, pk="id")
        try:
            chat = chats[chat_id]
            # Check ownership before deleting
            if not is_admin and chat.user_id != user_id:
                return JSONResponse({"error": "Forbidden"}, status_code=403)
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

    def _history_dropdown():
        return Div(
            Div(
                H2("History"),
                Button(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
                    ),
                    type="button",
                    id="history-close-btn",
                    cls="history-close-btn",
                    title="Close",
                    aria_label="Close history",
                ),
                cls="history-header",
            ),
            Div(
                Input(
                    type="text",
                    id="chat-search",
                    placeholder="Search Chat Name...",
                    cls="chat-search-input",
                ),
                cls="history-search",
            ),
            Div(
                Div(id="chat-list", cls="chat-list"),
                cls="history-content",
            ),
            cls="history-dropdown",
        )

    def _hero(user_info=None):
        # Get first letter of user's name for profile button
        user_initial = ""
        if user_info:
            name = user_info.get("name", "")
            if name:
                user_initial = name[0].upper()
            else:
                email = user_info.get("email", "")
                user_initial = email[0].upper() if email else "U"
        
        return Div(
            Div(
                H3(hero_title, cls="hero-title"),
                P(hero_subtitle, cls="hero-sub"),
                cls="space-y-2",
            ),
            Div(
                Button(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>'
                    ),
                    Span("New Chat"),
                    type="button",
                    id="new-chat-header-btn",
                    cls="navbar-btn",
                ),
                Button(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
                    ),
                    Span("History"),
                    type="button",
                    id="history-toggle-btn",
                    cls="navbar-btn",
                ),
                A(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>'
                    ),
                    Span("Logout"),
                    href="/logout",
                    cls="navbar-btn",
                ) if auth_required else None,
                Button(
                    Span(user_initial, cls="profile-initial"),
                    type="button",
                    id="profile-toggle-btn",
                    cls="profile-btn",
                    aria_label="Profile menu",
                    title="Profile menu",
                ) if auth_required else None,
                cls="flex gap-2 justify-end items-center",
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

    def _main_panel(user_info=None):
        return Div(
            _hero(user_info),
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
    
    def _profile_dropdown(user_info):
        user_name = user_info.get("name", "User") if user_info else "User"
        return Div(
            Div(
                H2("Account"),
                Button(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
                    ),
                    type="button",
                    id="profile-close-btn",
                    cls="history-close-btn",
                    title="Close",
                    aria_label="Close profile menu",
                ),
                cls="history-header",
            ),
            Div(
                P(user_name, cls="profile-user-name"),
                cls="profile-user-info",
            ),
            Div(
                Button(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>'
                    ),
                    Span("Download Chat"),
                    type="button",
                    cls="profile-menu-btn copy-chat-btn",
                    aria_label="Download conversation JSON",
                    title="Download conversation JSON",
                ),
                Button(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>'
                    ),
                    Span("Upload Chat"),
                    type="button",
                    cls="profile-menu-btn upload-chat-btn",
                    aria_label="Upload conversation JSON",
                    title="Upload conversation JSON",
                ),
                A(
                    NotStr(
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>'
                    ),
                    Span("Logout"),
                    href="/logout",
                    cls="profile-menu-btn profile-logout-btn",
                    aria_label="Logout",
                    title="Logout",
                ),
                Input(
                    type="file",
                    id="chat-upload",
                    accept="application/json",
                    cls="sr-only",
                ),
                cls="profile-menu-actions",
            ),
            cls="profile-dropdown",
        )

    def _shell(user_info=None):
        return Div(
            Div(id="sidebar-backdrop", cls="sidebar-backdrop"),
            _history_dropdown(),
            _profile_dropdown(user_info) if auth_required else None,
            _main_panel(user_info),
            _delete_chat_modal(),
            cls="app-shell",
        )

    @app.route("/")
    def home(request: Request):
        user_info = None
        if auth_required and not _is_authorized(request):
            request.session["next"] = "/"
            login_path = auth_paths["login_path"] if auth_paths else "/login"
            return RedirectResponse(login_path, status_code=303)
        if auth_required:
            user_info = request.session.get("auth")
        return (
            Title(hero_title),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(
                _shell(user_info),
                cls="min-h-screen",
                data_import_prefix=IMPORT_PREFIX,
            ),
        )

    return app
