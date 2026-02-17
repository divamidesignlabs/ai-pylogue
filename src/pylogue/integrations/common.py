import html
import json
import re
import ast
from typing import Any, Optional

PYLOGUE_INSTRUCTIONS = (
    "You are also a helpful AI assistant integrated with Pylogue enviroment."
    "The enviroment supports auto injection of html, i.e., if you respond with raw HTML it will be rendered as HTML."
    "The environment also supports markdown rendering, so you can use markdown syntax for formatting."
    "Finally the environment supports mermaid diagrams, so you can create diagrams using mermaid syntax. with ```mermaid ... ``` blocks."
    "Always generate (block appropriate) css based colorful mermaid diagrams (e.g., classDef evaporation fill:#add8e6,stroke:#333,stroke-width:2px) when appropriate to illustrate concepts."
    "also ensure in mermaid blocks you wrap the text with double quotes to avoid syntax errors, and <br> for line breaks instead of \\n"
    "prefer vertical layouts for flowcharts and sequence diagrams. "
    "Render math using LaTeX syntax within $$ ... $$ blocks or inline with $ ... $."
    "when embedding HTML do not wrap it inside ```html ... ``` blocks, just output the raw HTML directly. Do not add <html> or <body> tags."
    "Just because you can respond with HTML or generate mermaid diagrams does not mean you should always do that. Apart from accuracy of response, your next biggest goals is to save as many tokens as possible while ensuring the response is clear and complete."
)

_TOOL_HTML_RE = re.compile(r'<div class="tool-html">.*?</div>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_history_answer(answer: str) -> str:
    if not isinstance(answer, str) or not answer:
        return ""
    text = _TOOL_HTML_RE.sub("Rendered tool output.", answer)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def safe_json(value):
    if value is None:
        return "{}"
    if isinstance(value, str):
        try:
            return json.dumps(json.loads(value), indent=2, sort_keys=True, ensure_ascii=True)
        except json.JSONDecodeError:
            return value
    try:
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True)
    except TypeError:
        return json.dumps(str(value), indent=2, sort_keys=True, ensure_ascii=True)


def truncate(text: str, limit: int = 100) -> str:
    if not isinstance(text, str):
        return ""
    return text if len(text) <= limit else f"{text[:limit//2]} ... (truncated) ... {text[-limit//2:]}"


def safe_dom_id(value: str | None) -> str:
    if not value:
        return "tool-status"
    safe = []
    for ch in str(value):
        if ch.isalnum() or ch in {"-", "_"}:
            safe.append(ch)
    return "".join(safe) or "tool-status"


def format_tool_result_summary(tool_name: str, args, result):
    tool_label = html.escape(tool_name or "tool")
    safe_args = html.escape(safe_json(args))
    safe_result = html.escape(truncate(safe_json(result)))
    return (
        "\n\n"
        f'<details class="tool-call"><summary>Tool: {tool_label}</summary>'
        f"<div><strong>Args</strong></div>"
        f"<pre><code>{safe_args}</code></pre>"
        f"<div><strong>Result</strong></div>"
        f"<pre><code>{safe_result}</code></pre></details>\n\n"
    )


def format_tool_status_running(tool_name: str, args, call_id: str | None):
    purpose = None
    if isinstance(args, dict):
        purpose = args.get("purpose")
    label = purpose or (tool_name.replace("_", " ").title() if tool_name else "Working")
    status_id = safe_dom_id(f"tool-status-{call_id or ''}")
    safe_label = html.escape(str(label))
    return (
        f'<div id="{status_id}" class="tool-status tool-status--running">{safe_label}</div>\n'
    )


def format_tool_status_done(args, call_id: str | None, tool_name: str | None = None):
    purpose = None
    if isinstance(args, dict):
        purpose = args.get("purpose")
    
    # Use the same fallback logic as format_tool_status_running
    if purpose and isinstance(purpose, str) and purpose.strip():
        safe_label = purpose.strip()
    elif tool_name:
        safe_label = tool_name.replace("_", " ").title()
    else:
        safe_label = "Task"
    
    status_id = safe_dom_id(f"tool-status-{call_id or ''}")
    safe_label_escaped = html.escape(safe_label)
    # Show process name + highlighted completion status
    return (
        f'<div class="tool-status-update" data-target-id="{status_id}">'
        f'{safe_label_escaped} <span class="tool-status-check">✓Completed</span></div>\n'
    )


def resolve_tool_html(result):
    parsed_result = result
    if isinstance(parsed_result, str):
        stripped = parsed_result.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed_result = json.loads(stripped)
            except Exception:
                try:
                    parsed_result = ast.literal_eval(stripped)
                except Exception:
                    parsed_result = result
    if isinstance(parsed_result, dict) and "_pylogue_html_id" in parsed_result:
        token = parsed_result.get("_pylogue_html_id")
        try:
            from pylogue.embeds import take_html
        except Exception:
            return None
        return take_html(token)
    return None


def should_render_tool_result_raw(tool_name: str | None, result) -> bool:
    if not isinstance(result, str):
        return False
    stripped = result.lstrip()
    if not stripped.startswith("<"):
        return False
    return True


def wrap_tool_html(result: str) -> str:
    stripped = result.strip()
    if stripped.startswith("<div") and stripped.endswith("</div>"):
        return result
    return f'<div class="tool-html">{result}</div>'


def extract_user_from_context(context):
    if not isinstance(context, dict):
        return None
    user = context.get("user")
    return user if isinstance(user, dict) else None


def compose_system_prompt(
    base_prompt: str,
    additional_instructions: list[str],
    user: Optional[dict] = None,
    pylogue_instructions: str = PYLOGUE_INSTRUCTIONS,
) -> str:
    segments = []
    if base_prompt:
        segments.append(base_prompt)
    segments.append(pylogue_instructions)
    if isinstance(user, dict):
        display_name = user.get("display_name") or user.get("name")
        email = user.get("email")
        user_parts = []
        if display_name:
            user_parts.append(f"name={display_name}")
        if email:
            user_parts.append(f"email={email}")
        if user_parts:
            segments.append(
                "Authenticated user profile (source of truth): "
                + ", ".join(user_parts)
                + ". Use this identity when the user asks who they are or asks for personalization."
            )
    if additional_instructions:
        segments.extend(additional_instructions)
    return "\n\n".join(segments)


def get_export_state(prompt_state: dict, system_prompt: str) -> dict:
    return {
        "prompt_state": {
            "base_prompt": prompt_state.get("base_prompt", ""),
            "additional": list(prompt_state.get("additional", [])),
        },
        "system_prompt": system_prompt,
    }


def load_prompt_state(prompt_state: dict, meta: dict) -> None:
    if not isinstance(meta, dict):
        return
    exported_state = meta.get("prompt_state") if isinstance(meta.get("prompt_state"), dict) else {}
    if "base_prompt" in exported_state:
        prompt_state["base_prompt"] = exported_state.get("base_prompt") or ""
    if "additional" in exported_state and isinstance(exported_state.get("additional"), list):
        prompt_state["additional"] = list(exported_state.get("additional", []))
    elif isinstance(meta.get("system_prompt"), str):
        prompt_state["additional"] = [meta["system_prompt"]]
