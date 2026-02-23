# fasthtml solveit
from pylogue.shell import app_factory
from dotenv import load_dotenv
import logfire
from pylogue.integrations.pydantic_ai import PydanticAIResponder

load_dotenv(override=True)

logfire.configure(
    environment="development",
    service_name="optinn_ai_app",
)
logfire.instrument_pydantic_ai()

import sys
sys.path.append('/Users/yeshwanth/Code/Divami/client-projects/optinn/anveeksha/src/anveeksha/')
# sys.path.append('/home/yeshwanth/projects/optinn/anveeksha/src/anveeksha/')
from ChatSCM2_agent import rca_agent as agent
from ChatSCM2_agent.deps import Deps
from ChatSCM2_agent.config import config
from ChatSCM2_agent.oracle_client import OracleClient

db = OracleClient(
    user=config.oracle.user,
    password=config.oracle.password,
    host=config.oracle.host,
    port=config.oracle.port,
    service_name=config.oracle.service_name,
)
# Initialize dependencies
deps = Deps(
    db=db,
    owner="SCPOMGR",
    schema_cache={},
)

def _app_factory():
    return app_factory(
        responder_factory=lambda: PydanticAIResponder(agent=agent, agent_deps=deps),
        hero_title="OPTINN AI",
        hero_subtitle="Perform RCA and Scenario Analysis for SCM issues",
    )


if __name__ == "__main__":
    # run command "python -m scripts.examples.ai.optinn_chat"
    import uvicorn

    uvicorn.run(
        "scripts.examples.ai.pydanticai.optinn_app:_app_factory",
        host="0.0.0.0",
        port=5002,
        reload=True,
        factory=True,
    )
