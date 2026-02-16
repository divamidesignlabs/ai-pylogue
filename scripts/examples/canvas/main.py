from dotenv import load_dotenv
import logfire
from pydantic_ai import Agent

from canvas.main import main as canvas_app_factory
from canvas.state import CANVAS_STORE
from pylogue.integrations.pydantic_ai import PydanticAIResponder

load_dotenv(override=True)
logfire.configure(
    environment="development",
    service_name="pylogue-canvas-example",
)
logfire.instrument_pydantic_ai()

instructions = """
You are the canvas assistant.
Behavior contract:
1) If user asks to update/delete/create, you MUST use tools and complete the action in this same turn.
2) Use progressive reads: list_canvas_items first, then get_canvas_item only for selected ids.
3) If user refers to relative position (e.g. "last card"), resolve it from list_canvas_items rows.
4) For updates, always call update_canvas_item with both item_id and patch.
5) After mutations, run one verification read (list_canvas_items) before replying.
6) End every turn with plain text only (no JSON, no markdown tables), max 2 short sentences.

Operational defaults:
- New insight defaults: type=insight, col_span=4, row_span=1, variant=success.
- If required fields are missing, infer safe defaults and proceed.
- If a tool fails, explain the failure plainly and suggest the next single action.
"""

agent = Agent(
    "google-gla:gemini-2.5-flash-lite",
    instructions=instructions,
    retries=2,
    output_retries=4,
)


@agent.tool_plain()
def list_canvas_items(limit: int = 12, offset: int = 0):
    """List canvas items in compact progressive format."""
    return CANVAS_STORE.list_item_summaries(limit=limit, offset=offset)


@agent.tool_plain()
def get_canvas_item(item_id: str, level: str = "focus"):
    """Get one canvas item with progressive detail level: scan|focus|full."""
    return CANVAS_STORE.get_item_detail(item_id=item_id, level=level)


@agent.tool_plain()
def create_canvas_item(item: dict):
    """Create a new canvas item."""
    return CANVAS_STORE.create_item(item)


@agent.tool_plain()
def update_canvas_item(item_id: str, patch: dict):
    """Update fields on a canvas item by id."""
    return CANVAS_STORE.update_item(item_id, patch)


@agent.tool_plain()
def delete_canvas_item(item_id: str):
    """Delete a canvas item by id."""
    return {"deleted": CANVAS_STORE.delete_item(item_id)}


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
