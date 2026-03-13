# Core FastHTML + MonsterUI chat
from fasthtml.common import *
from monsterui.all import Theme, Container, ContainerT, TextPresets, Button, ButtonT, FastHTML as MUFastHTML, UkIcon
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from urllib.parse import quote_plus
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse
import asyncio
import inspect
import json
import base64
import html as html_lib
import logging
import os
import re

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

IMPORT_PREFIX = "__PYLOGUE_IMPORT__:"
STOP_PREFIX = "__PYLOGUE_STOP__:"
_CORE_STATIC_DIR = Path(__file__).resolve().parent / "static"
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    allowed_domains: tuple[str, ...] = ()
    allowed_emails: tuple[str, ...] = ()
    auth_required: bool = True
    session_secret: str | None = None


@dataclass(frozen=True)
class SimpleAuthConfig:
    username: str
    password: str
    auth_required: bool = True
    session_secret: str | None = None


def _split_csv_env(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def google_oauth_config_from_env() -> GoogleOAuthConfig | None:
    client_id = os.getenv("PYLOGUE_GOOGLE_CLIENT_ID") or os.getenv("PYLOGUE_CLIENT_ID")
    client_secret = os.getenv("PYLOGUE_GOOGLE_CLIENT_SECRET") or os.getenv("PYLOGUE_CLIENT_SECRET")
    if not (client_id and client_secret):
        return None
    return GoogleOAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        allowed_domains=_split_csv_env(os.getenv("PYLOGUE_GOOGLE_ALLOWED_DOMAINS")),
        allowed_emails=_split_csv_env(os.getenv("PYLOGUE_GOOGLE_ALLOWED_EMAILS")),
        auth_required=_env_bool("PYLOGUE_AUTH_REQUIRED", default=True),
        session_secret=os.getenv("PYLOGUE_SESSION_SECRET"),
    )


def simple_auth_config_from_env() -> SimpleAuthConfig | None:
    username = os.getenv("PYLOGUE_SIMPLE_AUTH_USERNAME")
    password = os.getenv("PYLOGUE_SIMPLE_AUTH_PASSWORD")
    if not (username and password):
        return None
    return SimpleAuthConfig(
        username=username,
        password=password,
        auth_required=_env_bool("PYLOGUE_AUTH_REQUIRED", default=True),
        session_secret=os.getenv("PYLOGUE_SESSION_SECRET"),
    )


def _get_admin_emails() -> set[str]:
    """Get set of admin emails from environment variable."""
    admin_emails = _split_csv_env(os.getenv("PYLOGUE_ADMIN_EMAILS"))
    return set(email.lower().strip() for email in admin_emails if email)


def _get_user_role(email: str | None) -> str:
    """Determine user role based on email. Returns 'admin' or 'user'."""
    if not email:
        return "user"
    admin_emails = _get_admin_emails()
    return "admin" if email.lower().strip() in admin_emails else "user"


def _normalize_base_path(base_path: str) -> str:
    base_path = (base_path or "").strip()
    if base_path in {"", "/"}:
        return ""
    normalized = "/" + base_path.strip("/")
    if ".." in normalized.split("/"):
        raise ValueError("base_path cannot contain '..'")
    return normalized


def _request_auth(request: Request):
    try:
        auth = request.session.get("auth")
    except Exception:
        auth = None
    if isinstance(auth, dict):
        return auth
    return None


def _connection_auth(conn):
    try:
        scope = conn.scope
    except Exception:
        scope = None
    if not isinstance(scope, dict):
        return None
    session = scope.get("session")
    if session is None:
        return None
    try:
        auth = session.get("auth")
    except Exception:
        auth = None
    if isinstance(auth, dict):
        return auth
    return None


def _user_context_from_auth(auth):
    if not isinstance(auth, dict):
        return None
    name = auth.get("name") or auth.get("username")
    email = auth.get("email")
    return {
        "name": name,
        "email": email,
        "display_name": name or email,
        "provider": auth.get("provider"),
    }


def _build_responder_context(conn):
    auth = _connection_auth(conn)
    if not auth:
        return None
    return {
        "auth": auth,
        "user": _user_context_from_auth(auth),
    }


def _invoke_responder(responder, prompt: str, context):
    try:
        signature = inspect.signature(responder)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        params = signature.parameters
        if "context" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        ):
            return responder(prompt, context=context)
    try:
        return responder(prompt)
    except TypeError:
        return responder(prompt, context)


def _oauth_base_url(request: Request) -> str:
    explicit = os.getenv("PYLOGUE_PUBLIC_URL")
    if explicit:
        return explicit.rstrip("/")
    base = str(request.base_url).rstrip("/")
    return base.replace("://0.0.0.0", "://localhost")


def _session_cookie_name() -> str:
    return os.getenv("PYLOGUE_SESSION_COOKIE", "pylogue_session")


def _register_google_auth_routes(app, cfg: GoogleOAuthConfig, base_path: str = "") -> dict[str, str]:
    try:
        from authlib.integrations.starlette_client import OAuth
    except Exception as exc:
        raise RuntimeError("Google OAuth requires authlib. Install with `pip install authlib`.") from exc

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
        client_kwargs={"scope": "openid email profile"},
    )

    base = _normalize_base_path(base_path)
    login_path = f"{base}/login" if base else "/login"
    login_google_path = f"{base}/login/google" if base else "/login/google"
    callback_path = f"{base}/auth/google/callback" if base else "/auth/google/callback"
    logout_path = f"{base}/logout" if base else "/logout"
    default_next = f"{base}/" if base else "/"

    @app.route(login_path, methods=["GET"])
    async def pylogue_google_login(request: Request):
        error = request.query_params.get("error")
        return Div(
            H2("Login", cls="uk-h2"),
            A(
                Span("Continue with Google", cls="text-sm font-semibold"),
                href=login_google_path,
                cls=(
                    "inline-flex items-center justify-center px-4 py-2 my-6 rounded-md "
                    "border border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-900 "
                    "hover:border-slate-900 transition-colors max-w-sm mx-auto"
                ),
            ),
            P(error, cls="text-red-500 mt-4") if error else None,
            cls="prose mx-auto mt-24 text-center",
        )

    @app.route(login_google_path)
    async def pylogue_google_login_redirect(request: Request):
        next_url = request.session.get("next") or request.query_params.get("next") or default_next
        request.session["next"] = next_url
        redirect_uri = _oauth_base_url(request) + callback_path
        return await oauth.google.authorize_redirect(request, redirect_uri)

    @app.route(callback_path)
    async def pylogue_google_callback(request: Request):
        try:
            token = await oauth.google.authorize_access_token(request)
            userinfo = token.get("userinfo")
            if not userinfo:
                try:
                    userinfo = await oauth.google.parse_id_token(request, token)
                except Exception:
                    # Fallback to userinfo endpoint when id_token is unavailable.
                    resp = await oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo", token=token)
                    userinfo = resp.json()
        except Exception as exc:
            _LOG.exception("Google OAuth callback failed: %s", exc)
            err = quote_plus(f"Google authentication failed ({type(exc).__name__})")
            return RedirectResponse(f"{login_path}?error={err}", status_code=303)

        email = userinfo.get("email") if isinstance(userinfo, dict) else None
        if not email:
            return RedirectResponse(f"{login_path}?error=Google+authentication+failed+(no+email)", status_code=303)
        if cfg.allowed_domains:
            if not email:
                return RedirectResponse(f"{login_path}?error=Google+account+not+allowed", status_code=303)
            domain = email.split("@")[-1]
            if domain not in cfg.allowed_domains:
                return RedirectResponse(f"{login_path}?error=Google+account+not+allowed", status_code=303)
        if cfg.allowed_emails and (not email or email not in cfg.allowed_emails):
            return RedirectResponse(f"{login_path}?error=Google+account+not+allowed", status_code=303)

        user_role = _get_user_role(email)
        request.session["auth"] = {
            "provider": "google",
            "email": email,
            "name": userinfo.get("name") if isinstance(userinfo, dict) else None,
            "picture": userinfo.get("picture") if isinstance(userinfo, dict) else None,
            "role": user_role,
        }
        next_url = request.session.pop("next", default_next)
        return RedirectResponse(next_url, status_code=303)

    @app.route(logout_path)
    async def pylogue_google_logout(request: Request):
        request.session.pop("auth", None)
        request.session.pop("next", None)
        return RedirectResponse(login_path, status_code=303)

    return {
        "login_path": login_path,
        "logout_path": logout_path,
        "default_next": default_next,
    }


def _register_simple_auth_routes(app, cfg: SimpleAuthConfig, base_path: str = "") -> dict[str, str]:
    base = _normalize_base_path(base_path)
    login_path = f"{base}/login" if base else "/login"
    logout_path = f"{base}/logout" if base else "/logout"
    default_next = f"{base}/" if base else "/"

    @app.route(login_path, methods=["GET", "POST"])
    async def pylogue_simple_login(request: Request):
        if request.method == "POST":
            form = await request.form()
            username = str(form.get("username") or "")
            password = str(form.get("password") or "")
            next_url = str(form.get("next") or request.session.get("next") or default_next)
            if compare_digest(username, cfg.username) and compare_digest(password, cfg.password):
                user_role = _get_user_role(cfg.username)
                request.session["auth"] = {
                    "provider": "simple",
                    "username": cfg.username,
                    "name": cfg.username,
                    "role": user_role,
                }
                request.session.pop("next", None)
                return RedirectResponse(next_url, status_code=303)
            return RedirectResponse(f"{login_path}?error=Invalid+username+or+password", status_code=303)

        next_url = request.query_params.get("next") or request.session.get("next") or default_next
        request.session["next"] = next_url
        error = request.query_params.get("error")
        return Div(
            H2("Login", cls="uk-h2"),
            Form(
                Input(type="text", name="username", placeholder="Username", required=True, cls="uk-input mb-3 rounded-md border border-white"),
                Input(type="password", name="password", placeholder="Password", required=True, cls="uk-input mb-3 rounded-md border border-white"),
                Input(type="hidden", name="next", value=next_url),
                Button("Sign in", type="submit", cls="uk-button uk-button-primary w-full border border-white rounded-md"),
                method="post",
                cls="max-w-sm mx-auto mt-6",
            ),
            P(error, cls="text-red-500 mt-4") if error else None,
            cls="prose mx-auto mt-24 text-center",
        )

    @app.route(logout_path)
    async def pylogue_simple_logout(request: Request):
        request.session.pop("auth", None)
        request.session.pop("next", None)
        return RedirectResponse(login_path, status_code=303)

    return {"login_path": login_path, "logout_path": logout_path, "default_next": default_next}


def register_core_static(app):
    if getattr(app, "_pylogue_static_registered", False):
        return
    app._pylogue_static_registered = True

    @app.route("/static/pylogue-core.css")
    def _pylogue_core_css():
        return FileResponse(_CORE_STATIC_DIR / "pylogue-core.css")

    @app.route("/static/pylogue-core.js")
    def _pylogue_core_js():
        return FileResponse(_CORE_STATIC_DIR / "pylogue-core.js")

    @app.route("/static/pylogue-markdown.js")
    def _pylogue_markdown_js():
        return FileResponse(_CORE_STATIC_DIR / "pylogue-markdown.js")

    @app.route("/favicon.svg")
    def _favicon():
        return FileResponse(_CORE_STATIC_DIR / "favicon.svg")

class EchoResponder:
    async def __call__(self, message: str, context=None):
        user = context.get("user") if isinstance(context, dict) else None
        display_name = user.get("display_name") if isinstance(user, dict) else None
        if display_name:
            response = f"[ECHO] {display_name}:\n{message}"
        else:
            response = f"[ECHO]:\n{message}"
        for ch in response:
            await asyncio.sleep(0.005)
            yield ch


def render_input():
    return Textarea(
        id="msg",
        name="msg",
        placeholder="Say hi...",
        autofocus=True,
        rows=1,
        cls="uk-textarea w-full bg-white border-slate-300 focus:border-slate-500 focus:ring-2 focus:ring-slate-200 font-mono",
    )


def render_cards(cards):
    rows = []
    data_json = json.dumps(cards)
    for card in cards:
        card_id = card.get("id", "")
        assistant_id = f"assistant-{card_id}" if card_id else ""
        rows.append(
            Div(
                Div(
                    NotStr('<svg width="27" height="27" viewBox="0 0 27 27" fill="none" xmlns="http://www.w3.org/2000/svg" class="user-icon"><circle cx="6.54545" cy="6.54545" r="6.54545" fill="#8FC187"/><circle cx="6.54545" cy="19.6364" r="6.54545" fill="#8FC187"/><circle cx="19.6364" cy="6.54545" r="6.54545" fill="#8FC187"/><circle cx="19.6364" cy="19.6364" r="6.54545" fill="#8FC187"/></svg>'),
                    Div(
                        card["question"],
                        data_raw_b64=base64.b64encode(card["question"].encode("utf-8")).decode("ascii"),
                        cls="marked text-base",
                    ),
                    cls="user-message-content",
                ),
                cls="chat-row-block chat-row-user",
            )
        )
        rows.append(
            Div(
                Div(
                    Button(
                        UkIcon("copy"),
                        cls="uk-button uk-button-text copy-btn",
                        type="button",
                        data_copy_target=assistant_id,
                        aria_label="Copy response",
                        title="Copy response",
                    ),
                    cls="flex justify-end",
                ),
                Div(
                    card["answer"] or "…",
                    id=assistant_id if assistant_id else None,
                    data_raw_b64=base64.b64encode((card["answer"] or "").encode("utf-8")).decode("ascii"),
                    cls="marked text-base text-left",
                ),
                cls="chat-row-block chat-row-assistant",
            )
        )
    
    # Only wrap in chat-panel if there are cards to display
    panel_content = [
        *rows,
        Div(id="scroll-anchor"),
        Input(type="hidden", id="chat-data", value=data_json),
        Input(type="hidden", id="chat-export", value=json.dumps({"cards": cards})),
    ]
    
    if cards:
        return Div(
            Div(
                *panel_content,
            ),
            id="cards",
            cls="chat-panel",
        )
    else:
        return Div(
            *panel_content,
            id="cards",
        )


def render_chat_data(cards):
    return Input(
        type="hidden",
        id="chat-data",
        value=json.dumps(cards),
        hx_swap_oob="true",
    )

_TOOL_HTML_RE = re.compile(r'<div class="tool-html">.*?</div>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_answer_for_history(answer: str) -> str:
    if not isinstance(answer, str) or not answer:
        return ""
    text = _TOOL_HTML_RE.sub("Rendered tool output.", answer)
    text = _TAG_RE.sub("", text)
    return html_lib.unescape(text).strip()


def build_export_payload(cards, responder=None):
    export_cards = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        answer = card.get("answer", "")
        answer_text = card.get("answer_text")
        if not isinstance(answer_text, str) or not answer_text.strip():
            answer_text = _normalize_answer_for_history(answer)
        export_card = dict(card)
        export_card["answer_text"] = answer_text
        export_cards.append(export_card)

    payload = {"cards": export_cards}
    if responder is not None and hasattr(responder, "get_export_state"):
        try:
            meta = responder.get_export_state()
        except Exception:
            meta = None
        if meta:
            payload["meta"] = meta
    return payload


def render_chat_export(cards, responder=None):
    payload = build_export_payload(cards, responder=responder)
    return Input(
        type="hidden",
        id="chat-export",
        value=json.dumps(payload),
        hx_swap_oob="true",
    )



def render_assistant_update(card):
    card_id = card.get("id", "")
    assistant_id = f"assistant-{card_id}" if card_id else ""
    return Div(
        card.get("answer", "") or "…",
        id=assistant_id if assistant_id else None,
        data_raw_b64=base64.b64encode((card.get("answer", "") or "").encode("utf-8")).decode("ascii"),
        cls="marked text-base text-left",
        hx_swap_oob="true",
    )


def get_core_headers(include_markdown: bool = True):
    headers = list(Theme.slate.headers())
    if include_markdown:
        headers.extend(
            [
                Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css"),
                Link(
                    rel="stylesheet",
                    href="https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/styles/github.min.css",
                ),
                Script(src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"),
                Script(src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"),
                Script(src="https://cdn.jsdelivr.net/npm/vega@5"),
                Script(src="https://cdn.jsdelivr.net/npm/vega-lite@5"),
                Script(src="https://cdn.jsdelivr.net/npm/vega-embed@6"),
            ]
        )
        headers.append(
            Script(src="https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/highlight.min.js")
        )
        headers.append(Script(src="./static/pylogue-markdown.js", type="module"))

    headers.append(Link(rel="stylesheet", href="./static/pylogue-core.css"))
    headers.append(Script(src="./static/pylogue-core.js", type="module"))
    headers.append(Link(rel="icon", href="./favicon.svg", type="image/svg+xml"))

    return headers


def register_ws_routes(
    app,
    responder=None,
    responder_factory=None,
    base_path: str = "",
    sessions: dict | None = None,
    auth_required: bool = False,
):
    if responder_factory is None:
        responder = responder or EchoResponder()
    base_path = _normalize_base_path(base_path)
    ws_path = f"{base_path}/ws" if base_path else "/ws"
    if sessions is None:
        sessions = {}

    def _on_connect(ws, send):
        if auth_required and not _connection_auth(ws):
            return
        session_context = _build_responder_context(ws)
        session_responder = responder_factory() if responder_factory else responder
        if hasattr(session_responder, "set_context"):
            try:
                session_responder.set_context(session_context)
            except Exception:
                pass
        ws_id = id(ws)
        sessions[ws_id] = {
            "cards": [],
            "responder": session_responder,
            "task": None,
            "context": session_context,
        }

    def _on_disconnect(ws):
        session = sessions.pop(id(ws), None)
        if session is None:
            return
        task = session.get("task")
        if task is not None and not task.done():
            task.cancel()

    @app.ws(ws_path, conn=_on_connect, disconn=_on_disconnect)
    async def ws_handler(msg: str, send, ws):
        if auth_required and not _connection_auth(ws):
            return
        ws_id = id(ws)
        session = sessions.get(ws_id)
        if session is None:
            session_context = _build_responder_context(ws)
            session_responder = responder_factory() if responder_factory else responder
            if hasattr(session_responder, "set_context"):
                try:
                    session_responder.set_context(session_context)
                except Exception:
                    pass
            session = {
                "cards": [],
                "responder": session_responder,
                "task": None,
                "context": session_context,
            }
            sessions[ws_id] = session
        cards = session["cards"]
        session_responder = session["responder"]
        current_task = session.get("task")
        context = _build_responder_context(ws)
        if context is not None:
            session["context"] = context
            if hasattr(session_responder, "set_context"):
                try:
                    session_responder.set_context(context)
                except Exception:
                    pass

        async def _run_message(prompt: str):
            cards.append({"id": str(len(cards)), "question": prompt, "answer": ""})
            await send(render_cards(cards))
            try:
                result = _invoke_responder(
                    session_responder,
                    prompt,
                    context=session.get("context"),
                )
                if inspect.isasyncgen(result):
                    async for chunk in result:
                        cards[-1]["answer"] += str(chunk)
                        await send(render_assistant_update(cards[-1]))
                else:
                    if inspect.isawaitable(result):
                        result = await result
                    for ch in str(result):
                        cards[-1]["answer"] += ch
                        await send(render_assistant_update(cards[-1]))
            except asyncio.CancelledError:
                if cards and cards[-1].get("answer"):
                    cards[-1]["answer"] += "\n\n[Stopped]"
                else:
                    cards[-1]["answer"] = "[Stopped]"
                await send(render_assistant_update(cards[-1]))
            finally:
                await send(render_chat_data(cards))
                await send(render_chat_export(cards, responder=session_responder))
                session["task"] = None
            return

        if isinstance(msg, str) and msg.startswith(IMPORT_PREFIX):
            if current_task is not None and not current_task.done():
                current_task.cancel()
            payload = msg[len(IMPORT_PREFIX) :].strip()
            try:
                imported = json.loads(payload) if payload else []
            except json.JSONDecodeError:
                imported = []
            meta = None
            if isinstance(imported, dict):
                meta = imported.get("meta")
                imported = imported.get("cards", [])
            normalized = []
            if isinstance(imported, list):
                if imported and all(isinstance(item, dict) and "role" in item for item in imported):
                    pending_question = None
                    for item in imported:
                        role = item.get("role")
                        content = item.get("content", "")
                        if role == "User":
                            pending_question = content
                        elif role == "Assistant":
                            if pending_question is None:
                                continue
                            normalized.append(
                                {
                                    "id": str(len(normalized)),
                                    "question": pending_question,
                                    "answer": content,
                                }
                            )
                            pending_question = None
                else:
                    for item in imported:
                        if not isinstance(item, dict):
                            continue
                        question = item.get("question")
                        answer = item.get("answer")
                        answer_text = item.get("answer_text")
                        if question is None or answer is None:
                            continue
                        normalized.append(
                            {
                                "id": str(len(normalized)),
                                "question": str(question),
                                "answer": str(answer),
                                "answer_text": str(answer_text) if answer_text is not None else None,
                            }
                        )
            session["cards"] = normalized
            if meta is not None and hasattr(session_responder, "load_state"):
                try:
                    session_responder.load_state(meta)
                except Exception:
                    pass
            if hasattr(session_responder, "load_history"):
                try:
                    session_responder.load_history(normalized, context=session.get("context"))
                except Exception:
                    pass
            await send(render_cards(normalized))
            await send(render_chat_data(normalized))
            await send(render_chat_export(normalized, responder=session_responder))
            return

        if isinstance(msg, str) and msg.startswith(STOP_PREFIX):
            if current_task is not None and not current_task.done():
                current_task.cancel()
            return

        if current_task is not None and not current_task.done():
            current_task.cancel()

        session["task"] = asyncio.create_task(_run_message(msg))
        return

    return sessions


def register_routes(
    app,
    responder=None,
    responder_factory=None,
    tag_line: str = "STREAMING DEMO",
    title: str = "Minimal Stream Chat",
    subtitle: str = "One question, one answer card. Response streams character-by-character.",
    base_path: str = "",
    inject_headers: bool = False,
    include_markdown: bool = True,
    tag_line_href: str = "",
    google_oauth_config: GoogleOAuthConfig | None = None,
    simple_auth_config: SimpleAuthConfig | None = None,
    auth_required: bool | None = None,
):
    if responder_factory is None and responder is not None and hasattr(responder, "message_history"):
        raise ValueError(
            "Responder appears to be stateful (has message_history). "
            "Pass responder_factory to create a fresh responder per connection."
        )
    register_core_static(app)
    base_path = _normalize_base_path(base_path)
    chat_path = f"{base_path}/" if base_path else "/"
    ws_path = f"{base_path}/ws" if base_path else "/ws"

    oauth_cfg = google_oauth_config or google_oauth_config_from_env()
    simple_cfg = simple_auth_config or simple_auth_config_from_env()
    if oauth_cfg and simple_cfg:
        raise ValueError("Configure either Google OAuth or simple auth, not both.")
    if auth_required is None:
        auth_required = bool(
            (oauth_cfg and oauth_cfg.auth_required) or (simple_cfg and simple_cfg.auth_required)
        )
    auth_paths = None
    if oauth_cfg:
        auth_paths = _register_google_auth_routes(app, oauth_cfg, base_path=base_path)
    elif simple_cfg:
        auth_paths = _register_simple_auth_routes(app, simple_cfg, base_path=base_path)
    elif auth_required:
        raise ValueError("auth_required=True needs Google OAuth or PYLOGUE_SIMPLE_AUTH_* env vars.")

    if inject_headers:
        for header in get_core_headers(include_markdown=include_markdown):
            app.hdrs = (*app.hdrs, header)

    if responder_factory is None:
        responder = responder or EchoResponder()
    register_ws_routes(
        app,
        responder=responder,
        responder_factory=responder_factory,
        base_path=base_path,
        auth_required=auth_required,
    )

    @app.route(chat_path)
    def home(request: Request):
        auth = _request_auth(request)
        if auth_required and not auth:
            request.session["next"] = chat_path
            login_path = auth_paths["login_path"] if auth_paths else "/login"
            return RedirectResponse(f"{login_path}?next={quote_plus(chat_path)}", status_code=303)
        # Use ASGI root_path so ws_connect is correct whether running standalone
        # or mounted under a prefix via FastAPI/Starlette app.mount().
        scope_root = request.scope.get("root_path", "").rstrip("/")
        effective_ws_path = f"{scope_root}/ws" if scope_root else ws_path

        tag_line_node = (
            A(
                tag_line,
                href=tag_line_href,
                cls="text-xs uppercase tracking-widest text-slate-500 hover:text-slate-700",
            )
            if tag_line_href
            else P(tag_line, cls="text-xs uppercase tracking-widest text-slate-500")
        )
        user_email = auth.get("email") if isinstance(auth, dict) else None
        logout_href = auth_paths["logout_path"] if auth_paths else "/logout"
        auth_bar = (
            Div(
                P(user_email or "Signed in", cls="text-xs text-slate-500"),
                A("Sign out", href=logout_href, cls="text-xs text-slate-700 hover:text-slate-900 underline"),
                cls="flex items-center justify-end gap-3",
            )
            if auth
            else None
        )
        return (
            Title(title),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Body(
                Container(
                    Div(
                        auth_bar,
                        Div(
                            tag_line_node,
                            H1(title, cls="text-3xl md:text-4xl font-semibold text-slate-900"),
                            P(subtitle, cls=(TextPresets.muted_sm, "text-slate-600")),
                            cls="space-y-2",
                        ),
                        Div(
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
                            cls="flex justify-end gap-2",
                        ),
                        Div(
                            Div(render_cards([])),
                            Form(
                                render_input(),
                                Div(
                                    Button("Send", cls=ButtonT.primary, type="submit", id="chat-send-btn"),
                                    cls="flex items-center",
                                ),
                                id="form",
                                hx_ext="ws",
                                ws_connect=effective_ws_path,
                                ws_send=True,
                                hx_target="#cards",
                                hx_swap="outerHTML",
                                cls="flex flex-col sm:flex-row gap-3 items-stretch pt-4",
                            ),
                            cls="chat-panel space-y-4",
                        ),
                        cls="space-y-6",
                    ),
                    cls=(ContainerT.lg, "py-10"),
                ),
                cls="min-h-screen bg-slate-50 text-slate-900",
            ),
        )

def main(
    responder=None,
    responder_factory=None,
    tag_line: str = "STREAMING DEMO",
    title: str = "Minimal Stream Chat",
    subtitle: str = "One question, one answer card. Response streams character-by-character.",
    include_markdown: bool = True,
    tag_line_href: str = "",
    google_oauth_config: GoogleOAuthConfig | None = None,
    simple_auth_config: SimpleAuthConfig | None = None,
    auth_required: bool | None = None,
    base_path: str = "",
):
    if responder is None:
        responder = EchoResponder()
    headers = get_core_headers(include_markdown=include_markdown)
    oauth_cfg = google_oauth_config or google_oauth_config_from_env()
    simple_cfg = simple_auth_config or simple_auth_config_from_env()
    if oauth_cfg and simple_cfg:
        raise ValueError("Configure either Google OAuth or simple auth, not both.")
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
    register_routes(
        app,
        responder=responder,
        responder_factory=responder_factory,
        tag_line=tag_line,
        title=title,
        subtitle=subtitle,
        tag_line_href=tag_line_href,
        base_path=base_path,
        google_oauth_config=oauth_cfg,
        simple_auth_config=simple_cfg,
        auth_required=auth_required,
    )
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pylogue.core:main", host="0.0.0.0", port=5001, reload=True, factory=True)
