from pylogue.canvas import app_factory
from pylogue.integrations.pydantic_ai import PydanticAIResponder
from ...agents.haiku import agent


def _app_factory():
    return app_factory(
        responder_factory=lambda: PydanticAIResponder(agent=agent, show_tool_details=False),
        title="Pylogue Canvas Alpha",
        subtitle="Blank 2D canvas + Pylogue core chat. Assistant can CRUD cards/content through typed action blocks.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scripts.examples.canvas.main:_app_factory",
        host="0.0.0.0",
        port=5012,
        reload=True,
        factory=True,
    )
