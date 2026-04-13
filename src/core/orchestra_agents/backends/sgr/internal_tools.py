"""SGR internal tool execution — reasoning, final answer, clarification, skills."""

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
    """Execute an internal SGR tool."""
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
    if parsed.tool_name == SGRInternalTools.clarification:
        return _execute_clarification_tool(backend, parsed)
    if parsed.tool_name == SGRInternalTools.list_skills:
        return _execute_list_skills()
    if parsed.tool_name == SGRInternalTools.get_skill_instructions:
        return _execute_get_skill_instructions(parsed)
    raise ValueError(f"Unknown internal tool: {parsed.tool_name}")


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


def _execute_list_skills() -> _support.ToolExecutionOutcome:
    """Return the skill menu for progressive disclosure."""
    from core.orchestra_agents.skills.registry import list_skills_menu

    return _support.ToolExecutionOutcome(
        tool_name=SGRInternalTools.list_skills,
        result_text=list_skills_menu(),
    )


def _execute_get_skill_instructions(
    parsed: _support.ParsedToolCall,
) -> _support.ToolExecutionOutcome:
    """Return full instructions for a specific skill."""
    from core.orchestra_agents.skills.registry import get_skill_instructions

    skill_id = str(parsed.arguments.get("skill_id") or "").strip()
    if not skill_id:
        return _support.ToolExecutionOutcome(
            tool_name=SGRInternalTools.get_skill_instructions,
            result_text="Error: skill_id is required",
            error="Missing skill_id parameter",
        )
    instructions = get_skill_instructions(skill_id)
    if instructions is None:
        return _support.ToolExecutionOutcome(
            tool_name=SGRInternalTools.get_skill_instructions,
            result_text=f"Error: skill '{skill_id}' not found",
            error=f"Unknown skill: {skill_id}",
        )
    return _support.ToolExecutionOutcome(
        tool_name=SGRInternalTools.get_skill_instructions,
        result_text=instructions,
    )
