# Pydantic AI integration for Pylogue
import asyncio
import copy
from typing import Any, Optional

from .common import (
    PYLOGUE_INSTRUCTIONS,
    compose_system_prompt as _compose_system_prompt_common,
    extract_user_from_context as _extract_user_from_context,
    format_tool_result_summary as _format_tool_result_summary,
    format_tool_status_done as _format_tool_status_done,
    format_tool_status_running as _format_tool_status_running,
    get_export_state as _get_export_state_common,
    load_prompt_state as _load_prompt_state_common,
    resolve_tool_html as _resolve_tool_html,
    sanitize_history_answer as _sanitize_history_answer,
    should_render_tool_result_raw as _should_render_tool_result_raw,
    wrap_tool_html as _wrap_tool_html,
)


def _get_tool_call_id(part):
    return getattr(part, "tool_call_id", None) or getattr(part, "call_id", None)


def _unwrap_tool_return(part_or_result, messages_module):
    if isinstance(part_or_result, messages_module.BaseToolReturnPart):
        return (
            part_or_result.tool_name,
            part_or_result.content,
            part_or_result.tool_call_id,
        )
    return None


def _extract_tool_result(event, messages_module):
    part = getattr(event, "part", None)
    if part is not None:
        tool_name = getattr(part, "tool_name", None) or getattr(part, "name", None)
        result = (
            getattr(part, "content", None)
            or getattr(part, "result", None)
            or getattr(part, "return_value", None)
            or getattr(part, "value", None)
        )
        call_id = _get_tool_call_id(part)
        return tool_name, result, call_id
    result = getattr(event, "result", None)
    tool_name = getattr(event, "tool_name", None)
    call_id = getattr(event, "tool_call_id", None) or getattr(event, "call_id", None)
    unwrapped = _unwrap_tool_return(result, messages_module)
    if unwrapped is not None:
        tool_name = tool_name or unwrapped[0]
        result = unwrapped[1]
        call_id = call_id or unwrapped[2]
    return tool_name, result, call_id


def _merge_user_into_deps(base_deps, context):
    user = context.get("user") if isinstance(context, dict) else None
    if not isinstance(user, dict):
        return base_deps

    # No baseline deps configured: pass a lightweight mapping as deps.
    if base_deps is None:
        return {"pylogue_user": user}

    # Common case for dict-based deps.
    if isinstance(base_deps, dict):
        merged = dict(base_deps)
        merged["pylogue_user"] = user
        return merged

    # Try to preserve existing deps type while attaching user context.
    try:
        merged = copy.copy(base_deps)
    except Exception:
        merged = base_deps
    try:
        setattr(merged, "pylogue_user", user)
        return merged
    except Exception:
        return base_deps


def _extract_user_from_deps(deps):
    if isinstance(deps, dict):
        user = deps.get("pylogue_user")
    else:
        user = getattr(deps, "pylogue_user", None)
    return user if isinstance(user, dict) else None


class PydanticAIResponder:
    """Streaming responder using Pydantic AI's run_stream_events."""
    pylogue_instructions = PYLOGUE_INSTRUCTIONS

    def __init__(
        self,
        agent: Any,
        agent_deps: Optional[Any] = None,
        show_tool_details: bool = True,
    ):
        self.agent = agent
        # Preserve any existing system prompt from the agent
        existing_prompt = getattr(agent, 'system_prompt', None) or ""
        base_prompt = existing_prompt if isinstance(existing_prompt, str) else ""
        # Share state on the agent to avoid multiple registrations
        state = getattr(agent, "_pylogue_prompt_state", None)
        if state is None:
            state = {
                "base_prompt": base_prompt,
                "additional": [],
            }
            agent._pylogue_prompt_state = state
        self._prompt_state = state
        self._base_agent_deps = agent_deps
        self.agent_deps = agent_deps
        self.message_history = None
        self.show_tool_details = show_tool_details
        self._active_user = None
        
        # Register dynamic system prompt function once per agent
        if not getattr(agent, "_pylogue_prompt_registered", False):
            @self.agent.system_prompt
            def custom_instructions(ctx) -> str:
                user = _extract_user_from_deps(getattr(ctx, "deps", None)) or self._active_user
                return self._compose_system_prompt(user)

            agent._pylogue_prompt_registered = True

    def append_instructions(self, additional_instructions: str) -> None:
        """Append additional instructions to the agent's system prompt."""
        if additional_instructions:
            self._prompt_state["additional"].append(additional_instructions)

    def _compose_system_prompt(self, user: Optional[dict] = None) -> str:
        return _compose_system_prompt_common(
            base_prompt=self._prompt_state.get("base_prompt", ""),
            additional_instructions=list(self._prompt_state.get("additional", [])),
            user=user,
            pylogue_instructions=self.pylogue_instructions,
        )

    def get_export_state(self) -> dict:
        """Return exportable system instruction state."""
        return _get_export_state_common(self._prompt_state, self._compose_system_prompt())

    def load_state(self, meta: dict) -> None:
        """Restore system instruction state from exported metadata."""
        _load_prompt_state_common(self._prompt_state, meta)

    def load_history(self, cards, context=None) -> None:
        """Load conversation history from Pylogue cards."""
        try:
            from pydantic_ai import messages as pai_messages
        except Exception:
            return
        history = []
        user = _extract_user_from_context(context)
        system_prompt = self._compose_system_prompt(user=user)
        if system_prompt:
            history.append(
                pai_messages.ModelRequest(
                    parts=[pai_messages.SystemPromptPart(content=system_prompt)]
                )
            )
        for card in cards or []:
            question = card.get("question")
            answer = card.get("answer")
            if question is not None:
                history.append(
                    pai_messages.ModelRequest(
                        parts=[pai_messages.UserPromptPart(content=str(question))]
                    )
                )
            answer_text = card.get("answer_text") if isinstance(card, dict) else None
            if answer_text is None:
                answer_text = answer
            answer_text = _sanitize_history_answer(answer_text)
            if answer_text:
                history.append(
                    pai_messages.ModelResponse(
                        parts=[pai_messages.TextPart(content=str(answer_text))]
                    )
                )
        self.message_history = history

    def set_context(self, context=None) -> None:
        user = _extract_user_from_context(context)
        self._active_user = user
        self.agent_deps = _merge_user_into_deps(self._base_agent_deps, {"user": user} if user else None)
    
    async def __call__(self, text: str, context=None):
        from pydantic_ai import messages
        from pydantic_ai.run import AgentRunResultEvent

        pending_tool_calls = {}
        tool_call_counter = 0

        # Keep deps up to date for this request context.
        self.set_context(context)

        async for event in self.agent.run_stream_events(
            text,
            message_history=self.message_history,
            deps=self.agent_deps,
        ):
            kind = getattr(event, "event_kind", "")

            if kind == "part_start" and isinstance(event.part, messages.TextPart):
                if event.part.content:
                    yield event.part.content
                continue

            if kind == "part_delta" and isinstance(event.delta, messages.TextPartDelta):
                if event.delta.content_delta:
                    yield event.delta.content_delta
                continue

            if kind == "function_tool_call":
                part = event.part
                tool_call_counter += 1
                call_id = _get_tool_call_id(part) or f"tool-{tool_call_counter}"
                pending_tool_calls[call_id] = (part.tool_name, part.args)
                if not self.show_tool_details:
                    yield _format_tool_status_running(part.tool_name, part.args, call_id)
                await asyncio.sleep(0)
                continue

            if kind == "builtin_tool_call":
                part = event.part
                tool_call_counter += 1
                call_id = _get_tool_call_id(part) or f"tool-{tool_call_counter}"
                pending_tool_calls[call_id] = (part.tool_name, part.args)
                if not self.show_tool_details:
                    yield _format_tool_status_running(part.tool_name, part.args, call_id)
                await asyncio.sleep(0)
                continue

            if kind in {
                "function_tool_result",
                "builtin_tool_result",
                "tool_result",
                "function_tool_return",
                "builtin_tool_return",
                "tool_return",
            }:
                tool_name, result, call_id = _extract_tool_result(event, messages)
                if call_id in pending_tool_calls:
                    tool_name, args = pending_tool_calls.pop(call_id)
                else:
                    args = None
                if tool_name or args or result:
                    resolved_html = _resolve_tool_html(result)
                    if not self.show_tool_details:
                        yield _format_tool_status_done(args, call_id, tool_name)
                    if resolved_html:
                        yield _wrap_tool_html(resolved_html)
                    elif _should_render_tool_result_raw(tool_name, result):
                        yield _wrap_tool_html(result)
                    elif self.show_tool_details:
                        yield _format_tool_result_summary(tool_name, args, result)
                await asyncio.sleep(0)
                continue

            if isinstance(event, AgentRunResultEvent):
                self.message_history = event.result.all_messages()
                if pending_tool_calls:
                    for tool_name, args in pending_tool_calls.values():
                        yield _format_tool_result_summary(tool_name, args, None)
