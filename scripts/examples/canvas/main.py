from dotenv import load_dotenv
import logfire
from pathlib import Path
from pydantic_ai import Agent

from canvas.agent_pack import build_canvas_instructions, install_canvas_tools
from canvas.components import RENDERERS
from canvas.main import main as canvas_app_factory
from canvas.state import CANVAS_STORE, configure_canvas_store
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

install_canvas_tools(agent, CANVAS_STORE)


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
