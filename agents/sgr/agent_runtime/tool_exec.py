"""SGR tool execution — MCP tool calls and outcome building."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.llm_proxy import protocol as _llm_proto
from core.orchestra_agents import agent_mux_runtime as _mux_rt

from agents.sgr.agent_runtime import support as _support

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.backend import SGRMinimaxBackend


async def process_tool_calls(
    backend: SGRMinimaxBackend,
    tool_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    outcome: _support.AgentTurnOutcome,
) -> None:
    """Execute all tool calls and append results to messages."""
    remaining = list(tool_calls)
    while remaining:
        tool_call = remaining.pop(0)
        parsed = _support.parse_tool_call(tool_call)
        outcome.tool_calls += 1
        outcome.used_tools.append(parsed.tool_name)
        execution = await execute_single(backend, tool_call)
        _apply_execution(execution, outcome)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": str(tool_call.get("id") or "").strip(),
                "content": execution.result_text or "(empty tool result)",
            }
        )


async def execute_single(
    backend: SGRMinimaxBackend,
    tool_call: dict[str, Any],
) -> _support.ToolExecutionOutcome:
    """Execute a single tool call via MCP server."""
    parsed = _support.parse_tool_call(tool_call)
    mcp_result = await backend._thread_ops.ensure_mcp_server().handle_tools_call(
        name=parsed.tool_name,
        arguments=parsed.arguments,
    )
    result_text = _llm_proto.flatten_content(mcp_result.get("content"))
    if not result_text:
        import json

        result_text = json.dumps(mcp_result, ensure_ascii=False)
    structured = mcp_result.get("structuredContent")
    if not isinstance(structured, dict):
        structured = {}
    if mcp_result.get("isError") or not structured.get("ok", True):
        return _support.ToolExecutionOutcome(tool_name=parsed.tool_name, result_text=result_text)
    return _build_tool_outcome(parsed, structured, result_text)


def _build_tool_outcome(
    parsed: _support.ParsedToolCall,
    structured: dict[str, Any],
    result_text: str,
) -> _support.ToolExecutionOutcome:
    outcome = _support.ToolExecutionOutcome(tool_name=parsed.tool_name, result_text=result_text)
    if parsed.tool_name == "thread_send":
        outcome.emitted_message = True
        outcome.message_preview = _mux_rt.message_preview(
            str(parsed.arguments.get("message") or ""),
            limit=160,
        )
        outcome.route = _support.normalize_optional_str(structured.get("route"))
        return outcome
    if parsed.tool_name == "thread_status":
        outcome.published_status = _support.normalize_optional_str(
            structured.get("published_status")
        ) or _support.normalize_optional_str(parsed.arguments.get("status"))
        outcome.message_preview = _mux_rt.message_preview(
            str(parsed.arguments.get("message") or ""),
            limit=160,
        )
    return outcome


def _apply_execution(
    execution: _support.ToolExecutionOutcome,
    outcome: _support.AgentTurnOutcome,
) -> None:
    if execution.emitted_message:
        outcome.messages_sent += 1
        outcome.last_reply_preview = execution.message_preview
    if execution.published_status:
        outcome.statuses_published += 1
        outcome.last_published_status = execution.published_status
        outcome.last_status_preview = execution.message_preview
