"""Internal tool execution implementation for the canonical SGR backend."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from core.orchestra_agents.backends.sgr import internal_tools as _internal_tools
from core.orchestra_agents.backends.sgr import support as _support
from core.orchestra_agents.backends.sgr import tool_result as _tool_result
from core.orchestra_agents.backends.sgr.sgr_tools import SGRInternalTools

if TYPE_CHECKING:
    from core.orchestra_agents.backends.sgr.backend import SGRMinimaxBackend

logger = logging.getLogger(__name__)


class _MessagePreview(Protocol):
    def __call__(self, text: str, *, limit: int = 200) -> str: ...


async def process_tool_calls(
    backend: SGRMinimaxBackend,
    tool_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    outcome: _support.AgentTurnOutcome,
    *,
    message_preview: _MessagePreview,
) -> None:
    """Execute all tool calls and append results to messages."""
    remaining = list(tool_calls)
    while remaining:
        tool_call = remaining.pop(0)
        parsed = _support.parse_tool_call(tool_call)
        outcome.tool_calls += 1
        outcome.used_tools.append(parsed.tool_name)
        execution = await execute_single(
            backend,
            tool_call,
            message_preview=message_preview,
        )
        _apply_execution(execution, outcome)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": str(tool_call.get("id") or "").strip(),
                "content": execution.result_text or "(empty tool result)",
            },
        )


async def execute_single(
    backend: SGRMinimaxBackend,
    tool_call: dict[str, Any],
    *,
    message_preview: _MessagePreview,
) -> _support.ToolExecutionOutcome:
    """Execute a single tool call via internal tools or injected MCP servers."""
    parsed = _support.parse_tool_call(tool_call)
    logger.info("Executing SGR tool call %s", parsed.tool_name)
    if parsed.tool_name in SGRInternalTools.names:
        return _internal_tools.execute_internal_tool(backend, parsed)
    try:
        mcp_result = await _execute_mcp_tool(backend, parsed)
    except Exception as exc:
        logger.error("SGR tool call failed for %s: %s", parsed.tool_name, exc)
        return _build_error_outcome(parsed.tool_name, exc)
    result_text = _tool_result.result_text(mcp_result)
    structured = _tool_result.structured_content(mcp_result)
    if mcp_result.get("isError") or not structured.get("ok", True):
        error_msg = str(structured.get("error") or "tool returned ok=false")
        return _support.ToolExecutionOutcome(
            tool_name=parsed.tool_name,
            result_text=result_text,
            error=error_msg,
        )
    return _build_tool_outcome(
        parsed,
        structured,
        result_text,
        message_preview=message_preview,
    )


async def _execute_mcp_tool(
    backend: SGRMinimaxBackend,
    parsed: _support.ParsedToolCall,
) -> dict[str, Any]:
    """Route a tool call to the appropriate injected MCP server."""
    server = backend._mcp_servers.get(parsed.tool_name)
    if server is None:
        raise RuntimeError(f"No MCP server registered for tool: {parsed.tool_name}")
    return await server.handle_tools_call(
        name=parsed.tool_name,
        arguments=dict(parsed.arguments),
    )


def _build_error_outcome(
    tool_name: str,
    error: Exception,
) -> _support.ToolExecutionOutcome:
    """Build a tool execution outcome for an error."""
    return _support.ToolExecutionOutcome(
        tool_name=tool_name,
        result_text=f"Error: {error}",
        error=str(error),
    )


def _build_tool_outcome(
    parsed: _support.ParsedToolCall,
    structured: dict[str, Any],
    result_text: str,
    *,
    message_preview: _MessagePreview,
) -> _support.ToolExecutionOutcome:
    """Build a tool execution outcome from MCP result."""
    outcome = _support.ToolExecutionOutcome(tool_name=parsed.tool_name, result_text=result_text)
    msg_text = str(parsed.arguments.get("message") or "")
    if "send" in parsed.tool_name and structured.get("ok", False):
        outcome.emitted_message = True
        outcome.message_preview = message_preview(msg_text, limit=160)
    if "status" in parsed.tool_name and (
        structured.get("published_status") or structured.get("ok")
    ):
        outcome.published_status = _support.normalize_optional_str(
            structured.get("published_status"),
        ) or _support.normalize_optional_str(parsed.arguments.get("status"))
        outcome.message_preview = message_preview(msg_text, limit=160)
    return outcome


def _apply_execution(
    execution: _support.ToolExecutionOutcome,
    outcome: _support.AgentTurnOutcome,
) -> None:
    """Apply a single tool execution result to the turn outcome."""
    if execution.error:
        outcome.tool_errors += 1
    if execution.emitted_message:
        outcome.messages_sent += 1
        outcome.last_reply_preview = execution.message_preview
    if execution.published_status:
        outcome.statuses_published += 1
        outcome.last_published_status = execution.published_status
        outcome.last_status_preview = execution.message_preview
