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
Use progressive reading: scan with list_canvas_items first, then inspect one item with get_canvas_item.
When changing canvas state, prefer small explicit updates.
Keep responses concise and practical.
After any tool call, always return a short plain-text response for the user.
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
