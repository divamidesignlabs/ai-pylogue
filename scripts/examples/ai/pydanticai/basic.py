# fasthtml solveit
import random
import os
from typing import Any

import logfire
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pylogue.dashboarding import render_plotly_chart_py
from pylogue.shell import app_factory
from pylogue.integrations.pydantic_ai import PydanticAIResponder

load_dotenv(override=True)


def _configure_simple_login_defaults() -> None:
    # Keep the demo protected by default; callers can override via env/.env.
    os.environ.setdefault("PYLOGUE_AUTH_REQUIRED", "true")
    os.environ.setdefault("PYLOGUE_SIMPLE_AUTH_USERNAME", "user")
    os.environ.setdefault("PYLOGUE_SIMPLE_AUTH_PASSWORD", "password")
    os.environ.setdefault("PYLOGUE_SESSION_SECRET", "pylogue-dev-session-secret-change-me")


_configure_simple_login_defaults()

logfire.configure(
    environment="development",
    service_name="pylogue-haiku-example",
)
logfire.instrument_pydantic_ai()

instructions = """
You talk as little as you can, while being helpful
"""

agent = Agent(
    "google-gla:gemini-3-flash-preview",
    instructions=instructions,
)
deps = None


def _resolve_sql_query_runner(ctx: RunContext[Any]):
    deps_obj = ctx.deps
    if isinstance(deps_obj, dict):
        runner = deps_obj.get("sql_query_runner")
        if callable(runner):
            return runner
    runner = getattr(deps_obj, "sql_query_runner", None)
    if callable(runner):
        return runner
    return None


@agent.tool
def render_chart(ctx: RunContext[Any], sql_query: str, plotly_python_code: str):
    runner = _resolve_sql_query_runner(ctx)
    return render_plotly_chart_py(
        sql_query_runner=runner,
        sql_query=sql_query if runner else None,
        plotly_python=plotly_python_code,
    )

render_chart.__doc__ = render_plotly_chart_py.__doc__

@agent.tool
def inspect_user_context(ctx: RunContext[Any], purpose: str = "verifying user context"):
    """Inspect runtime deps and return the authenticated user payload from Pylogue."""
    deps_obj = ctx.deps
    if isinstance(deps_obj, dict):
        user = deps_obj.get("pylogue_user")
    else:
        user = getattr(deps_obj, "pylogue_user", None)
    if not isinstance(user, dict):
        return {
            "ok": False,
            "message": "No pylogue_user found in ctx.deps",
            "session_sig": f"haiku-{random.randint(1000, 9999)}",
        }
    return {
        "ok": True,
        "name": user.get("display_name") or user.get("name"),
        "email": user.get("email"),
        "provider": user.get("provider"),
        "session_sig": f"haiku-{random.randint(1000, 9999)}",
    }


def _app_factory():
    return app_factory(
        responder_factory=lambda: PydanticAIResponder(
            agent=agent,
            agent_deps=deps,
            show_tool_details=False,
        ),
        hero_title="Haiku Assistant",
        hero_subtitle="Answers in 5-7-5 haikus with streaming responses.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scripts.examples.ai.pydanticai.basic:_app_factory",
        host="0.0.0.0",
        port=6004,
        reload=True,
        factory=True,
    )
