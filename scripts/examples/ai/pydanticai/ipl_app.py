# fasthtml solveit
from dotenv import load_dotenv

from pylogue.integrations.pydantic_ai import PydanticAIResponder
from pylogue.shell import app_factory
from scripts.agents.ipl.main import agent as ipl_agent

load_dotenv(override=True)


def _app_factory():
    return app_factory(
        responder_factory=lambda: PydanticAIResponder(
            agent=ipl_agent,
            agent_deps=None,
            show_tool_details=True,
        ),
        hero_title="IPL Dashboard Agent",
        hero_subtitle="Ask questions about IPL data and get responsive Plotly charts.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scripts.examples.ai.pydanticai.ipl_app:_app_factory",
        host="0.0.0.0",
        port=5005,
        reload=True,
        factory=True,
    )
