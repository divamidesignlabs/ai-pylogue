# fasthtml solveit
from dotenv import load_dotenv
from pylogue.shell import app_factory
from pylogue.integrations.agno import AgnoResponder, logfire_instrument_agno
from pylogue.dashboarding import render_plotly_chart_py
import sys
sys.path.append("/Users/yeshwanth/Code/Personal/agno/cookbook/01_showcase/01_agents/text_to_sql")

load_dotenv(override=True)
logfire_instrument_agno()

from agent import sql_agent, sql_tool

def sql_query_runner(sql_query: str):
    return sql_tool.run_sql(sql_query)

def render_chart(sql_query: str, plotly_python: str):
    return render_plotly_chart_py(sql_query_runner=sql_query_runner, sql_query=sql_query, plotly_python=plotly_python)

render_chart.__doc__ = render_plotly_chart_py.__doc__

sql_agent.set_tools([render_chart])

def _app_factory():
    return app_factory(
        responder_factory=lambda: AgnoResponder(agent=sql_agent),
        hero_title="F1 Dashboard Agent",
        hero_subtitle="Ask questions about the F1 database and get SQL queries in response.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scripts.examples.ai.agno.f1_app:_app_factory",
        host="0.0.0.0",
        port=5003,
        reload=True,
        factory=True,
    )
