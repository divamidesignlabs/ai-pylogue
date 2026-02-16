from dotenv import load_dotenv
import logfire
from pathlib import Path
from pydantic_ai import Agent, RunContext
from typing import Any

from canvas.agent_pack import build_canvas_instructions, install_canvas_tools
from canvas.components import RENDERERS
from canvas.main import main as canvas_app_factory
from canvas.state import (
    configure_canvas_store,
    get_canvas_store,
    list_canvas_ids,
    publish_canvas_message,
)
from pylogue.dashboarding import render_plotly_chart_py
from pylogue.embeds import get_html
from pylogue.integrations.pydantic_ai import PydanticAIResponder

load_dotenv(override=True)
logfire.configure(
    environment="development",
    service_name="pylogue-canvas-example",
)
logfire.instrument_pydantic_ai()

STORE_PATH = Path(__file__).with_suffix(".store.json")
configure_canvas_store(STORE_PATH)

COMPONENT_TYPES = ", ".join(sorted(RENDERERS.keys()))
instructions = build_canvas_instructions(COMPONENT_TYPES)

agent = Agent(
    "google-gla:gemini-2.5-flash-lite",
    instructions=instructions,
    retries=2,
    output_retries=4,
)

install_canvas_tools(agent, get_canvas_store, list_canvas_ids, publish_canvas_message=publish_canvas_message)
_LAST_CHART_HTML_ID: str | None = None


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
    """Render a Plotly chart with Python code that defines `fig`."""
    global _LAST_CHART_HTML_ID
    runner = _resolve_sql_query_runner(ctx)
    result = render_plotly_chart_py(
        sql_query_runner=runner,
        sql_query=sql_query if runner else None,
        plotly_python=plotly_python_code,
    )
    if isinstance(result, dict):
        token = result.get("_pylogue_html_id")
        if isinstance(token, str) and token.strip():
            _LAST_CHART_HTML_ID = token.strip()
    return result


render_chart.__doc__ = render_plotly_chart_py.__doc__


def _resolve_canvas_id(ctx: RunContext[Any], canvas_id: str = "") -> str:
    selected = (canvas_id or "").strip()
    if selected:
        return selected
    deps = getattr(ctx, "deps", None)
    canvas = deps.get("pylogue_canvas") if isinstance(deps, dict) else getattr(deps, "pylogue_canvas", None)
    if isinstance(canvas, dict):
        current = str(canvas.get("current_canvas_id") or "").strip()
        if current:
            return current
    return "main"


@agent.tool
def pin_last_chart_to_canvas(
    ctx: RunContext[Any],
    title: str = "Chart",
    canvas_id: str = "",
    col_span: int = 12,
    row_span: int = 2,
):
    """Persist the most recently rendered chart into a canvas as an HTML card."""
    token = (_LAST_CHART_HTML_ID or "").strip()
    if not token:
        return {"ok": False, "error": "No rendered chart found in this session."}
    html = get_html(token)
    if not html:
        return {"ok": False, "error": "Rendered chart expired. Please re-render and try again."}
    store = get_canvas_store(_resolve_canvas_id(ctx, canvas_id))
    created = store.create_item(
        {
            "type": "html",
            "title": title or "Chart",
            "item_description": f"chart card: {title or 'Chart'}",
            "html": html,
            "col_span": max(1, min(int(col_span), 12)),
            "row_span": max(1, min(int(row_span), 6)),
            "variant": "success",
        }
    )
    return {"ok": True, "canvas_id": _resolve_canvas_id(ctx, canvas_id), "item_id": created.get("id")}


def _app_factory():
    return canvas_app_factory(
        responder_factory=lambda: PydanticAIResponder(
            agent=agent,
            agent_deps=None,
            show_tool_details=True,
        )
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scripts.examples.canvas.main:_app_factory",
        host="0.0.0.0",
        port=5006,
        reload=True,
        factory=True,
    )
