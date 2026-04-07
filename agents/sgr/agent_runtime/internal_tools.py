from __future__ import annotations

import json
from dataclasses import asdict

from agents.sgr.agent_runtime import internal_tool_support as _tool_support
from agents.sgr.agent_runtime import support as _support
from agents.sgr.agent_runtime import tool_result as _tool_result
from agents.sgr.agent_runtime.sgr_tools import (
    ClarificationToolArgs,
    FinalAnswerToolArgs,
    ReasoningToolArgs,
    SGRInternalTools,
)
from core.orchestra_agents import agent_mux_runtime as _mux_rt


async def execute_internal_tool(
    backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    if parsed.tool_name == SGRInternalTools.reasoning:
        return _execute_reasoning_tool(backend, parsed)
    if parsed.tool_name == SGRInternalTools.final_answer:
        return await _execute_final_answer_tool(backend, parsed)
    return await _execute_clarification_tool(backend, parsed)


def _execute_reasoning_tool(
    backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    arguments = ReasoningToolArgs.from_arguments(parsed.arguments)
    note = " | ".join(arguments.reasoning_steps)
    _tool_support.context_memory(backend).add_entry(
        thread_id=None,
        entry_type="reasoning",
        text=f"{arguments.current_situation}: {note}",
        metadata_summary=arguments.plan_status,
    )
    return _support.ToolExecutionOutcome(
        tool_name=parsed.tool_name,
        result_text=json.dumps(asdict(arguments), ensure_ascii=False),
    )


async def _execute_final_answer_tool(
    backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    arguments = FinalAnswerToolArgs.from_arguments(parsed.arguments)
    return await _send_internal_message(
        backend=backend,
        tool_name=parsed.tool_name,
        message=arguments.answer,
        metadata_summary=arguments.reasoning,
    )


async def _execute_clarification_tool(
    backend: object,
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    arguments = ClarificationToolArgs.from_arguments(parsed.arguments)
    message = _clarification_message(arguments)
    return await _send_internal_message(
        backend=backend,
        tool_name=parsed.tool_name,
        message=message,
        metadata_summary=arguments.reasoning,
    )


def _clarification_message(arguments: ClarificationToolArgs) -> str:
    questions = "\n".join(f"- {question}" for question in arguments.questions)
    return f"Need clarification before I continue:\n{questions}"


async def _send_internal_message(
    *,
    backend: object,
    tool_name: str,
    message: str,
    metadata_summary: str,
) -> _support.ToolExecutionOutcome:
    mcp_result = (
        await _tool_support.thread_ops(backend)
        .ensure_mcp_server()
        .handle_tools_call(
            name="thread_send",
            arguments={"message": message},
        )
    )
    _tool_support.context_memory(backend).add_entry(
        thread_id=None,
        entry_type=tool_name,
        text=message,
        metadata_summary=metadata_summary,
    )
    return _support.ToolExecutionOutcome(
        tool_name=tool_name,
        result_text=_tool_result.flatten_content(mcp_result.get("content")),
        emitted_message=True,
        message_preview=_mux_rt.message_preview(message, limit=160),
    )
