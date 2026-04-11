"""Compatibility facade for SGR tool execution helpers."""

from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.agent_mux.normalization import (
    message_preview as _message_preview,
)
from core.orchestra_agents.backends.sgr import support as _support
from core.orchestra_agents.backends.sgr.backend import SGRMinimaxBackend
from core.orchestra_agents.backends.sgr.tools.execution import (
    _apply_execution as _apply_execution,
)
from core.orchestra_agents.backends.sgr.tools.execution import (
    _build_error_outcome as _build_error_outcome,
)
from core.orchestra_agents.backends.sgr.tools.execution import (
    _build_tool_outcome as _internal_build_tool_outcome,
)
from core.orchestra_agents.backends.sgr.tools.execution import (
    _execute_mcp_tool as _execute_mcp_tool,
)
from core.orchestra_agents.backends.sgr.tools.execution import (
    execute_single as _execute_single,
)
from core.orchestra_agents.backends.sgr.tools.execution import (
    process_tool_calls as _process_tool_calls,
)


async def process_tool_calls(
    backend: SGRMinimaxBackend,
    tool_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    outcome: _support.AgentTurnOutcome,
) -> None:
    """Execute all tool calls and append results to messages."""
    await _process_tool_calls(
        backend,
        tool_calls,
        messages,
        outcome,
        message_preview=_message_preview,
    )


async def execute_single(
    backend: SGRMinimaxBackend,
    tool_call: dict[str, Any],
) -> _support.ToolExecutionOutcome:
    """Execute a single tool call via internal tools or injected MCP servers."""
    return await _execute_single(
        backend,
        tool_call,
        message_preview=_message_preview,
    )


def _build_tool_outcome(
    parsed: _support.ParsedToolCall,
    structured: dict[str, Any],
    result_text: str,
) -> _support.ToolExecutionOutcome:
    """Build a tool execution outcome from MCP result."""
    return _internal_build_tool_outcome(
        parsed,
        structured,
        result_text,
        message_preview=_message_preview,
    )
