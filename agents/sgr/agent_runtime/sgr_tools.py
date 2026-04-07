from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agents.sgr.agent_runtime import sgr_tool_support as _support

_CLARIFICATION_REASONING_MAX = 2048


@dataclass(frozen=True)
class ReasoningToolArgs:
    reasoning_steps: list[str]
    current_situation: str
    plan_status: str
    enough_data: bool
    remaining_steps: list[str]
    task_completed: bool

    @classmethod
    def from_arguments(cls, arguments: dict[str, Any]) -> ReasoningToolArgs:
        return cls(
            reasoning_steps=_support.string_list(
                arguments.get("reasoning_steps"),
                minimum=2,
                maximum=3,
            ),
            current_situation=_support.bounded_text(
                arguments.get("current_situation"),
                field_name="current_situation",
                maximum=300,
            ),
            plan_status=_support.bounded_text(
                arguments.get("plan_status"),
                field_name="plan_status",
                maximum=150,
            ),
            enough_data=bool(arguments.get("enough_data")),
            remaining_steps=_support.string_list(
                arguments.get("remaining_steps"),
                minimum=0,
                maximum=3,
            ),
            task_completed=bool(arguments.get("task_completed")),
        )


@dataclass(frozen=True)
class FinalAnswerToolArgs:
    reasoning: str
    completed_steps: list[str]
    answer: str
    status: Literal["completed", "failed"]

    @classmethod
    def from_arguments(cls, arguments: dict[str, Any]) -> FinalAnswerToolArgs:
        status = _support.final_status(arguments.get("status"))
        if status is None:
            raise ValueError("final_answer_tool status must be 'completed' or 'failed'")
        return cls(
            reasoning=_support.required_text(arguments.get("reasoning"), field_name="reasoning"),
            completed_steps=_support.string_list(
                arguments.get("completed_steps"),
                minimum=1,
                maximum=5,
            ),
            answer=_support.required_text(arguments.get("answer"), field_name="answer"),
            status=status,
        )


@dataclass(frozen=True)
class ClarificationToolArgs:
    reasoning: str
    unclear_terms: list[str]
    assumptions: list[str]
    questions: list[str]
    reasoning_was_truncated: bool

    @classmethod
    def from_arguments(cls, arguments: dict[str, Any]) -> ClarificationToolArgs:
        reasoning, reasoning_was_truncated = _support.bounded_text_with_truncation(
            arguments.get("reasoning"),
            field_name="reasoning",
            maximum=_CLARIFICATION_REASONING_MAX,
        )
        return cls(
            reasoning=reasoning,
            unclear_terms=_support.string_list(
                arguments.get("unclear_terms"),
                minimum=1,
                maximum=3,
            ),
            assumptions=_support.string_list(
                arguments.get("assumptions"),
                minimum=2,
                maximum=3,
            ),
            questions=_support.string_list(
                arguments.get("questions"),
                minimum=1,
                maximum=3,
            ),
            reasoning_was_truncated=reasoning_was_truncated,
        )


class SGRInternalTools:
    reasoning = "reasoning_tool"
    final_answer = "final_answer_tool"
    clarification = "clarification_tool"
    names = frozenset((reasoning, final_answer, clarification))

    @classmethod
    def build_openai_tools(cls) -> list[dict[str, Any]]:
        return [
            _tool_entry(
                name=cls.reasoning,
                description="Record a structured reasoning step before deciding what to do next.",
                properties={
                    "reasoning_steps": _array_prop(),
                    "current_situation": _string_prop(),
                    "plan_status": _string_prop(),
                    "enough_data": {"type": "boolean"},
                    "remaining_steps": _array_prop(),
                    "task_completed": {"type": "boolean"},
                },
                required=[
                    "reasoning_steps",
                    "current_situation",
                    "plan_status",
                    "task_completed",
                ],
            ),
            _tool_entry(
                name=cls.final_answer,
                description="Record the final answer internally. Use an MCP send tool to deliver it.",
                properties={
                    "reasoning": _string_prop(),
                    "completed_steps": _array_prop(),
                    "answer": _string_prop(),
                    "status": {"type": "string", "enum": ["completed", "failed"]},
                },
                required=["reasoning", "completed_steps", "answer", "status"],
            ),
            _tool_entry(
                name=cls.clarification,
                description="Record a clarification question internally. Use an MCP send tool to ask it.",
                properties={
                    "reasoning": _string_prop(),
                    "unclear_terms": _array_prop(),
                    "assumptions": _array_prop(),
                    "questions": _array_prop(),
                },
                required=["reasoning", "unclear_terms", "assumptions", "questions"],
            ),
        ]


def _tool_entry(
    name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _string_prop() -> dict[str, str]:
    return {"type": "string"}


def _array_prop() -> dict[str, Any]:
    return {"type": "array", "items": _string_prop()}
