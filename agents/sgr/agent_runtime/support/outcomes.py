"""Tool execution and agent turn outcome models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agents.sgr.agent_runtime.support.settings import normalize_optional_str
from core.orchestra_agents.agent_mux_runtime import message_preview


@dataclass
class ToolExecutionOutcome:
    tool_name: str
    result_text: str
    emitted_message: bool = False
    published_status: str | None = None
    message_preview: str | None = None
    route: str | None = None
    error: str | None = None


@dataclass
class AgentTurnOutcome:
    llm_turns: int = 0
    tool_calls: int = 0
    messages_sent: int = 0
    statuses_published: int = 0
    tool_errors: int = 0
    used_tools: list[str] = field(default_factory=list)
    direct_text_ignored: bool = False
    ignored_text_preview: str | None = None
    last_reply_preview: str | None = None
    last_status_preview: str | None = None
    last_published_status: str | None = None
    no_action_warning: bool = False
    event_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def action_emitted(self) -> bool:
        return self.messages_sent > 0 or self.statuses_published > 0


@dataclass(frozen=True)
class ParsedToolCall:
    tool_name: str
    arguments: dict[str, Any]


def parse_tool_call(tool_call: dict[str, Any]) -> ParsedToolCall:
    function = tool_call.get("function") if isinstance(tool_call, dict) else {}
    if not isinstance(function, dict):
        function = {}
    tool_name = normalize_optional_str(function.get("name")) or "unknown_tool"
    raw_arguments = function.get("arguments")
    try:
        if isinstance(raw_arguments, dict):
            arguments = dict(raw_arguments)
        elif isinstance(raw_arguments, str) and raw_arguments.strip():
            arguments = json.loads(raw_arguments)
        else:
            arguments = {}
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return ParsedToolCall(tool_name=tool_name, arguments=arguments)


def handle_direct_text_retry(
    assistant_text: str,
    messages: list[dict[str, Any]],
    outcome: AgentTurnOutcome,
    direct_text_retries: int,
    max_direct_text_retries: int,
) -> tuple[bool, int]:
    outcome.direct_text_ignored = True
    outcome.ignored_text_preview = message_preview(assistant_text, limit=160)
    if outcome.action_emitted:
        return False, direct_text_retries
    if direct_text_retries >= max_direct_text_retries:
        return False, direct_text_retries
    messages.append(
        {
            "role": "system",
            "content": (
                "Direct assistant text helps you think, but it will not be forwarded externally. "
                "If you want the peer to receive something, use an available MCP send tool. "
                "Only MCP tool calls produce externally visible actions."
            ),
        }
    )
    return True, direct_text_retries + 1
