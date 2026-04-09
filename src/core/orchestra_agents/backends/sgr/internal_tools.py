"""SGR internal tool execution — reasoning, final answer, clarification."""

from __future__ import annotations

import json
from dataclasses import asdict

from core.orchestra_agents.backends.sgr import support as _support
from core.orchestra_agents.backends.sgr.sgr_tools import (
    ClarificationToolArgs,
    FinalAnswerToolArgs,
    ReasoningToolArgs,
    SGRInternalTools,
)


def execute_internal_tool(
    backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    """Execute an internal SGR tool (reasoning, final_answer, clarification)."""
    try:
        return _execute_internal_tool(backend, parsed)
    except ValueError as exc:
        return _support.ToolExecutionOutcome(
            tool_name=parsed.tool_name,
            result_text=f"Technical note: invalid {parsed.tool_name} arguments. {exc}",
            error=str(exc),
        )


def _execute_internal_tool(
    backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    if parsed.tool_name == SGRInternalTools.reasoning:
        return _execute_reasoning_tool(backend, parsed)
    if parsed.tool_name == SGRInternalTools.final_answer:
        return _execute_final_answer_tool(backend, parsed)
    return _execute_clarification_tool(backend, parsed)


def _execute_reasoning_tool(
    _backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    """Record a structured reasoning step."""
    arguments = ReasoningToolArgs.from_arguments(parsed.arguments)
    return _support.ToolExecutionOutcome(
        tool_name=parsed.tool_name,
        result_text=json.dumps(asdict(arguments), ensure_ascii=False),
    )


def _execute_final_answer_tool(
    _backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    """Return structured final answer for the LLM to act on."""
    arguments = FinalAnswerToolArgs.from_arguments(parsed.arguments)
    return _support.ToolExecutionOutcome(
        tool_name=parsed.tool_name,
        result_text=json.dumps(asdict(arguments), ensure_ascii=False),
    )


def _execute_clarification_tool(
    _backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    """Return structured clarification for the LLM to act on."""
    arguments = ClarificationToolArgs.from_arguments(parsed.arguments)
    questions = "\n".join(f"- {question}" for question in arguments.questions)
    message = f"Need clarification before I continue:\n{questions}"
    technical_context: list[str] = []
    if arguments.reasoning_was_truncated:
        technical_context.append(
            "Technical note: clarification_tool reasoning exceeded 2048 characters and was truncated before execution. "
            "Keep future clarification reasoning shorter and continue from the truncated context."
        )
    return _support.ToolExecutionOutcome(
        tool_name=parsed.tool_name,
        result_text=json.dumps(
            {
                "message": message,
                "technical_context": technical_context,
                **asdict(arguments),
            },
            ensure_ascii=False,
        ),
    )
