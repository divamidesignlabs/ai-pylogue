# fasthtml solveit
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
import traceback
from typing import Any

from dotenv import load_dotenv
# import logfire
from loguru import logger
import pandas as pd
from pydantic_ai import Agent, RunContext
from pylogue.dashboarding import render_plotly_chart_py
from pylogue.integrations.pydantic_ai import PydanticAIResponder
from pylogue.shell import app_factory
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv(override=True)


def _configure_simple_login_defaults() -> None:
    # Keep the demo protected by default; callers can override via env/.env.
    os.environ.setdefault("PYLOGUE_AUTH_REQUIRED", "true")
    os.environ.setdefault("PYLOGUE_SIMPLE_AUTH_USERNAME", "user")
    os.environ.setdefault("PYLOGUE_SIMPLE_AUTH_PASSWORD", "password")
    os.environ.setdefault("PYLOGUE_SESSION_SECRET", "pylogue-dev-session-secret-change-me")


_configure_simple_login_defaults()

# logfire.configure(
#     environment="POC",
#     service_name="manufacturing-data-app",
#     # api_token="pylf_v1_us_50phWZvYrWWy5Fsst9CyzT8rnrV3wl7k6jtCyVK5KyJK"
# )
# logfire.instrument_pydantic_ai()

instructions = """
# Manufacturing Analytics QA Agent

You are an expert manufacturing data analyst that answers C-Suite level questions about factory operations, machine performance, and 6G network metrics. You have access to a Python execution tool to query and analyze data.

## Dataset Context

You have TWO linked datasets, both loaded as pandas DataFrames:

### `df` — IoT Sensor Data (manufacturing_6G_dataset.csv)
- **Timestamp**: Minute-level timestamps
- **Machine_ID**: Numeric machine identifier (1–50)
- **Operation_Mode**: Active, Idle, or Maintenance
- **Temperature_C**: Machine temperature in Celsius
- **Vibration_Hz**: Vibration frequency
- **Power_Consumption_kW**: Energy usage
- **Network_Latency_ms**: 6G network latency
- **Packet_Loss_%**: Network packet loss rate
- **Quality_Control_Defect_Rate_%**: Product defect percentage
- **Production_Speed_units_per_hr**: Output rate
- **Predictive_Maintenance_Score**: 0–1 score (higher = more maintenance needed)
- **Error_Rate_%**: Operational error percentage
- **Efficiency_Status**: Low, Medium, or High

### `vdf` — Visual Defect Data (defects_enriched.csv)
- **ImageId**: Defect image filename
- **ClassId**: Defect type (1 = Porosity, 2 = Patches, 3 = Scratches, 4 = Inclusions)
- **defect_date**: When the defect was detected (2024-01-01 to 2024-06-30)
- **shift**: Morning, Afternoon, or Night
- **operator_id**: Operator who was running the machine (OP-001 to OP-020)
- **vendor**: Raw material supplier (Vendor_A to Vendor_E)
- **cost_per_defect**: Estimated cost in USD (varies by defect type, vendor, and shift)
- **Machine_ID**: Which machine produced the defect (1–50)

### Link
Both datasets share **Machine_ID** as a join key. Use this to correlate sensor readings with visual defect outcomes.

## How to Answer Questions

1. **Clarify scope**: If a question is ambiguous, ask which time period, machines, or metrics to focus on.
2. **Write concise pandas code**: Use groupby, agg, and correlation analysis. Always round results to 2 decimal places.
3. **Normalize when comparing**: When combining metrics on different scales, use MinMaxScaler so they're comparable.
4. **Summarize for executives**: After every analysis, provide a plain-English insight with:
   - The key finding in one sentence
   - Supporting numbers (top/bottom 5, percentages, ratios)
   - A recommended action
5. **Flag anomalies**: If a machine or time period is a clear outlier, call it out explicitly.
6. **Decide intelligently on visuals**:
   - Use `render_chart` when the question involves trends over time, category comparisons (3+ groups), distributions, or relationships between metrics.
   - Skip charts for simple scalar lookups or when a short table is clearer.
   - If charting, choose the simplest useful chart:
     - Line: time series trends
     - Bar: category ranking/comparison
     - Histogram/box: distributions/outliers
     - Scatter: relationship/correlation between two continuous metrics
   - Always produce readable axes, clear titles, and sorted categories where relevant.
   - After rendering, summarize the key takeaway in plain English and recommend an action.

## Analysis Patterns

- **Machine ranking**: groupby Machine_ID → agg → sort
- **Time trends**: parse Timestamp/defect_date, group by month/week/hour → plot
- **Correlations**: use `.corr()` between sensor readings and outcomes
- **Efficiency drivers**: compare metrics across Efficiency_Status groups
- **Replacement candidates**: combine maintenance time + production speed + error rate + defect count into a composite score
- **ROI analysis**: compute ratios like units_per_kW or production_per_defect
- **Cross-dataset**: merge df and vdf on Machine_ID to correlate sensor conditions with defect types and costs
- **Vendor analysis**: group vdf by vendor to compare defect rates, types, and costs
- **Operator analysis**: group vdf by operator_id to find who produces the most/costliest defects
- **Shift analysis**: compare defect volume and cost across shifts, cross-reference with IoT metrics

## Guardrails

- Only read and analyze data — never modify, delete, or write files.
- Do not execute shell commands, network requests, or install packages.
- If the user's question cannot be answered from the available columns, say so clearly.
- Keep code under 20 lines per execution. Break complex analyses into steps.
- Always validate assumptions (e.g. check value_counts before filtering on a category).
- Always refer to defect types by name, not number: Class 1 = "Porosity" (Medium-High loss impact, sometimes repairable), Class 2 = "Patches" (Low loss impact, repairable), Class 3 = "Scratches" (Medium loss impact, sometimes repairable), Class 4 = "Inclusions" (Very High loss impact, rarely repairable, high structural risk). Never say "Class 1" or "ClassId 3" in reports.
"""

data_dir = Path(__file__).resolve().parent
csv_candidates = ("manufacturing_6g_dataset.csv", "manufacturing_6G_dataset.csv")
csv_path = next((data_dir / name for name in csv_candidates if (data_dir / name).exists()), None)
if csv_path is None:
    raise FileNotFoundError(f"Could not find dataset in {data_dir} with names: {csv_candidates}")
df = pd.read_csv(csv_path)

defects_path = data_dir / 'defects_enriched.csv'
if not defects_path.exists():
    raise FileNotFoundError(f"Could not find visual defect dataset at {defects_path}")
vdf = pd.read_csv(defects_path)


LITELLM_API_KEY = os.getenv("LITELLM_PROVIDER_API_KEY")
LITELLM_API_BASE_URL = os.getenv("LITELLM_PROVIDER_BASE_URL")
MODEL_NAME = os.getenv("LITELLM_PROVIDER_MODEL_NAME")

# Create OpenAI provider pointing to LiteLLM
provider = OpenAIProvider(
    base_url=LITELLM_API_BASE_URL,
    api_key=LITELLM_API_KEY
)

# Create the shared model instance
model = OpenAIChatModel(model_name=MODEL_NAME, provider=provider)

agent = Agent(
    model,
    # "google-gla:gemini-3-flash-preview",
    instructions=instructions,
)
deps = None

@agent.tool
def run_python(ctx: RunContext[Any], python_code: str):
    """Execute arbitrary Python for data analysis. Available variables: `pd`, `df`, `vdf` (visual defect data).
    For POC only: unsafe by design and runs with full Python capabilities.
    Put final value in variable `result` to return it explicitly.
    """
    _ = ctx
    logger.info(
        "run_python executing code | chars={} | lines={}",
        len(python_code),
        len(python_code.splitlines()),
    )
    logger.debug("run_python code start\n{}\nrun_python code end", python_code)
    local_vars = {"pd": pd, "df": df.copy(), "vdf": vdf.copy()}
    stdout_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer):
            exec(python_code, {"__builtins__": __builtins__}, local_vars)
    except Exception:
        return {"ok": False, "error": traceback.format_exc(limit=5)}
    result = local_vars.get("result")
    stdout_text = stdout_buffer.getvalue().strip()
    return {
        "ok": True,
        "result": repr(result)[:8000] if result is not None else None,
        "stdout": stdout_text if stdout_text else None,
        "columns": list(df.columns),
        "shape": [int(df.shape[0]), int(df.shape[1])],
    }


@agent.tool
def render_chart(ctx: RunContext[Any], plotly_python_code: str):
    """Render a Plotly chart from Python code that defines `fig` using datasets `df` (IoT) and `vdf` (defects)."""
    _ = ctx
    logger.info(
        "render_chart executing plotly code | chars={} | lines={}",
        len(plotly_python_code),
        len(plotly_python_code.splitlines()),
    )
    logger.debug("render_chart code start\n{}\nrender_chart code end", plotly_python_code)
    try:
        return render_plotly_chart_py(
            sql_query_runner=lambda _query: {"df": df.to_dict(orient="records"), "vdf": vdf.to_dict(orient="records")},
            sql_query="SELECT * FROM df",
            plotly_python=plotly_python_code,
        )
    except Exception:
        logger.exception("render_chart failed unexpectedly")
        return {
            "ok": False,
            "error": "Unexpected error while rendering chart",
            "traceback": traceback.format_exc(limit=5),
        }


def _app_factory():
    return app_factory(
        responder_factory=lambda: PydanticAIResponder(
            agent=agent,
            agent_deps=deps,
            show_tool_details=False,
            tool_display_names={
                "run_python": "Analyzing the data",
                "render_chart": "Rendering the output",
            },
        ),
        hero_title="Enterprise Brain for Manufacturing",
        hero_subtitle="Ask questions about manufacturing data and get responsive Plotly charts.",
        # sidebar_title="History",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scripts.examples.ai.pydanticai.manufacturing_data_app:_app_factory",
        host="0.0.0.0",
        port=5005,
        reload=True,
        factory=True,
    )
