# Agno integration for Pylogue
import copy
import inspect
import os
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


def logfire_instrument_agno(
    *,
    write_token: str | None = None,
    endpoint: str = "https://logfire-us.pydantic.dev",
    service_name: str = "pylogue-agno",
    use_batch_processor: bool = True,
):
    """Instrument Agno with OpenTelemetry and export spans to Logfire via OTLP."""
    resolved_write_token = write_token or os.getenv("LOGFIRE_TOKEN") or os.getenv("LOGFIRE_WRITE_TOKEN")
    if not resolved_write_token:
        raise ValueError(
            "Missing Logfire write token. Set LOGFIRE_TOKEN (or LOGFIRE_WRITE_TOKEN) or pass write_token=..."
        )

    try:
        from openinference.instrumentation.agno import AgnoInstrumentor
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Agno Logfire instrumentation requires `openinference-instrumentation-agno`."
        ) from exc

    try:
        from opentelemetry import trace as trace_api
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Agno Logfire instrumentation requires OpenTelemetry SDK packages."
        ) from exc

    resolved_endpoint = endpoint.rstrip("/")
    resource = Resource.create({"service.name": service_name}) if service_name else None
    tracer_provider = TracerProvider(resource=resource)
    span_processor_cls = BatchSpanProcessor if use_batch_processor else SimpleSpanProcessor
    tracer_provider.add_span_processor(
        span_processor_cls(
            OTLPSpanExporter(
                endpoint=f"{resolved_endpoint}/v1/traces",
                headers={"Authorization": resolved_write_token},
            )
        )
    )
    trace_api.set_tracer_provider(tracer_provider)
    AgnoInstrumentor().instrument()
    return tracer_provider


def _normalize_tool_payload(tool_entry: Any) -> tuple[str | None, Any, Any, str | None]:
    if isinstance(tool_entry, dict):
        function = tool_entry.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            function_args = function.get("arguments")
        else:
            function_name = None
            function_args = None

        tool_name = (
            tool_entry.get("tool_name")
            or tool_entry.get("name")
            or function_name
            or tool_entry.get("tool")
        )
        args = (
            tool_entry.get("tool_args")
            or tool_entry.get("args")
            or tool_entry.get("arguments")
            or function_args
            or tool_entry.get("input")
        )
        result = (
            tool_entry.get("result")
            or tool_entry.get("output")
            or tool_entry.get("content")
            or tool_entry.get("observation")
        )
        call_id = tool_entry.get("tool_call_id") or tool_entry.get("call_id") or tool_entry.get("id")
    else:
        tool_name = (
            getattr(tool_entry, "tool_name", None)
            or getattr(tool_entry, "name", None)
            or getattr(tool_entry, "tool", None)
        )
        args = (
            getattr(tool_entry, "tool_args", None)
            or getattr(tool_entry, "args", None)
            or getattr(tool_entry, "arguments", None)
            or getattr(tool_entry, "input", None)
        )
        result = (
            getattr(tool_entry, "result", None)
            or getattr(tool_entry, "output", None)
            or getattr(tool_entry, "content", None)
            or getattr(tool_entry, "observation", None)
        )
        call_id = (
            getattr(tool_entry, "tool_call_id", None)
            or getattr(tool_entry, "call_id", None)
            or getattr(tool_entry, "id", None)
        )
    return tool_name, args, result, call_id


def _extract_tools(chunk) -> list[tuple[str | None, Any, Any, str | None]]:
    payloads: list[Any] = []

    tools = getattr(chunk, "tools", None)
    if isinstance(tools, list):
        payloads.extend(tools)
    elif tools is not None:
        payloads.append(tools)

    # Agno ToolCallStarted/ToolCallCompleted events expose singular `tool`.
    tool = getattr(chunk, "tool", None)
    if tool is not None:
        payloads.append(tool)

    # Some providers can expose tool executions directly.
    tool_executions = getattr(chunk, "tool_executions", None)
    if isinstance(tool_executions, list):
        payloads.extend(tool_executions)
    elif tool_executions is not None:
        payloads.append(tool_executions)

    return [_normalize_tool_payload(t) for t in payloads]


def _is_event(event_value, expected_name: str) -> bool:
    if event_value is None:
        return False
    event_str = str(event_value)
    return event_str == expected_name or event_str.endswith(expected_name)


def _extract_content_text(chunk: Any) -> str | None:
    content = getattr(chunk, "content", None)
    if content is None:
        return None
    if isinstance(content, str):
        return content
    return str(content)


def _extract_reasoning_text(chunk: Any) -> str | None:
    reasoning_content = getattr(chunk, "reasoning_content", None)
    if reasoning_content is None:
        return None
    if isinstance(reasoning_content, str):
        return reasoning_content
    return str(reasoning_content)


def _message_to_dict(message: Any) -> dict | None:
    if isinstance(message, dict):
        role = message.get("role")
        content = message.get("content")
        if role is None or content is None:
            return None
        return {"role": role, "content": str(content)}
    role = getattr(message, "role", None)
    content = getattr(message, "content", None)
    if role is None or content is None:
        return None
    return {"role": str(role), "content": str(content)}


def _normalize_history_messages(messages: Any) -> list[dict]:
    if not isinstance(messages, list):
        return []
    normalized = []
    for message in messages:
        converted = _message_to_dict(message)
        if converted is not None:
            normalized.append(converted)
    return normalized


class AgnoResponder:
    """Streaming responder using Agno's stream events."""

    pylogue_instructions = PYLOGUE_INSTRUCTIONS

    def __init__(
        self,
        agent: Any,
        show_tool_details: bool = True,
        run_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.agent = agent
        existing_instructions = getattr(agent, "instructions", None)
        if isinstance(existing_instructions, str):
            base_prompt = existing_instructions
        elif isinstance(existing_instructions, (list, tuple)):
            base_prompt = "\n".join(str(p) for p in existing_instructions if p is not None)
        else:
            base_prompt = ""

        state = getattr(agent, "_pylogue_prompt_state", None)
        if state is None:
            state = {
                "base_prompt": base_prompt,
                "additional": [],
            }
            agent._pylogue_prompt_state = state

        self._prompt_state = state
        self.message_history = []
        self.show_tool_details = show_tool_details
        self._active_user = None
        self.run_kwargs = copy.deepcopy(run_kwargs) if isinstance(run_kwargs, dict) else {}

    def append_instructions(self, additional_instructions: str) -> None:
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
        return _get_export_state_common(self._prompt_state, self._compose_system_prompt())

    def load_state(self, meta: dict) -> None:
        _load_prompt_state_common(self._prompt_state, meta)

    def load_history(self, cards, context=None) -> None:
        history = []
        for card in cards or []:
            question = card.get("question")
            answer = card.get("answer")
            if question is not None:
                history.append({"role": "user", "content": str(question)})
            answer_text = card.get("answer_text") if isinstance(card, dict) else None
            if answer_text is None:
                answer_text = answer
            answer_text = _sanitize_history_answer(answer_text)
            if answer_text:
                history.append({"role": "assistant", "content": str(answer_text)})
        self.message_history = history
        self.set_context(context)

    def set_context(self, context=None) -> None:
        self._active_user = _extract_user_from_context(context)

    def _build_run_input(self, text: str):
        history = list(self.message_history or [])
        history.append({"role": "user", "content": str(text)})
        return history

    def _build_run_kwargs(self) -> dict[str, Any]:
        kwargs = copy.deepcopy(self.run_kwargs)
        user = self._active_user
        if isinstance(user, dict) and "user_id" not in kwargs:
            user_id = user.get("email") or user.get("display_name") or user.get("name")
            if isinstance(user_id, str) and user_id:
                kwargs["user_id"] = user_id
        return kwargs

    async def __call__(self, text: str, context=None):
        self.set_context(context)
        user = self._active_user
        try:
            run_call_result = self.agent.arun(
                self._build_run_input(text),
                stream=True,
                stream_events=True,
                additional_context=self._compose_system_prompt(user=user),
                **self._build_run_kwargs(),
            )
            if inspect.isawaitable(run_call_result):
                run_stream = await run_call_result
            else:
                run_stream = run_call_result
        except ModuleNotFoundError as exc:
            raise RuntimeError("Agno integration requires the `agno` package. Install it with `pip install agno`.") from exc
        except AttributeError as exc:
            raise RuntimeError("Configured Agno agent does not expose `arun`.") from exc

        if not hasattr(run_stream, "__aiter__"):
            raise TypeError(
                "Agno `arun(..., stream=True, stream_events=True)` must return an async iterable."
            )

        pending_tool_calls: dict[str, tuple[str | None, Any]] = {}
        tool_call_counter = 0
        streamed_text = ""
        history_updated_from_stream = False

        async for chunk in run_stream:
            event = getattr(chunk, "event", None)

            if _is_event(event, "RunContent") or _is_event(event, "RunIntermediateContent") or _is_event(event, "RunResponse") or _is_event(event, "RunCompleted"):
                content = _extract_content_text(chunk)
                if content:
                    if content.startswith(streamed_text):
                        delta = content[len(streamed_text) :]
                        streamed_text = content
                    else:
                        delta = content
                        streamed_text += content
                    if delta:
                        yield delta
                continue

            if _is_event(event, "ToolCallStarted"):
                for tool_name, args, _, call_id in _extract_tools(chunk):
                    tool_call_counter += 1
                    resolved_call_id = call_id or f"tool-{tool_call_counter}"
                    pending_tool_calls[resolved_call_id] = (tool_name, args)
                    if not self.show_tool_details:
                        yield _format_tool_status_running(tool_name, args, resolved_call_id)
                continue

            if _is_event(event, "ToolCallCompleted"):
                for tool_name, args, result, call_id in _extract_tools(chunk):
                    resolved_call_id = call_id
                    if resolved_call_id in pending_tool_calls:
                        tool_name, args = pending_tool_calls.pop(resolved_call_id)
                    if self.show_tool_details and (tool_name or args or result):
                        yield _format_tool_result_summary(tool_name, args, result)
                    if not self.show_tool_details:
                        yield _format_tool_status_done(args, resolved_call_id, tool_name)
                    resolved_html = _resolve_tool_html(result)
                    if resolved_html:
                        yield _wrap_tool_html(resolved_html)
                    elif _should_render_tool_result_raw(tool_name, result):
                        yield _wrap_tool_html(result)
                continue

            reasoning_text = _extract_reasoning_text(chunk)
            if reasoning_text and (_is_event(event, "ReasoningContentDelta") or _is_event(event, "Reasoning")):
                yield reasoning_text

            content = _extract_content_text(chunk)
            if content and _is_event(event, "Reasoning"):
                yield content

            messages = _normalize_history_messages(getattr(chunk, "messages", None))
            if messages:
                self.message_history = messages
                history_updated_from_stream = True

        if pending_tool_calls and self.show_tool_details:
            for tool_name, args in pending_tool_calls.values():
                yield _format_tool_result_summary(tool_name, args, None)

        if not history_updated_from_stream:
            updated_history = list(self.message_history) if isinstance(self.message_history, list) else []
            updated_history.append({"role": "user", "content": str(text)})
            updated_history.append({"role": "assistant", "content": streamed_text})
            self.message_history = updated_history
