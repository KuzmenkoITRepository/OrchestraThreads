"""SGR turn execution — LLM loop and message building."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agents.sgr.agent_runtime import model_routing as _model_routing
from agents.sgr.agent_runtime import support as _support
from agents.sgr.agent_runtime import tool_exec as _tools
from core.orchestra_agents import runtime as _rt

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.backend import SGRMinimaxBackend


async def run_turn(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    primary_event: Any,
    session_key: str,
    peer_agent_slug: str,
) -> _support.AgentTurnOutcome:
    """Execute the full LLM tool loop for one event."""
    messages = _build_messages(backend, session_key, peer_agent_slug, delivery, primary_event)
    outcome = _support.AgentTurnOutcome()
    retries = 0
    step = 0
    while step < backend.settings.max_reasoning_steps:
        step += 1
        should_stop, retries = await _run_step(
            backend,
            messages,
            outcome,
            retries,
            primary_event,
        )
        if should_stop:
            break
    return outcome


async def _run_step(
    backend: SGRMinimaxBackend,
    messages: list[dict[str, Any]],
    outcome: _support.AgentTurnOutcome,
    retries: int,
    event: Any,
) -> tuple[bool, int]:
    """Run a single LLM reasoning step."""
    outcome.llm_turns += 1
    msg, text, calls = backend._llm.extract_completion(
        await backend._llm.chat_completion(_chat_payload(backend, messages, event)),
        backend.llm_config.model or "gpt-5.4",
    )
    messages.append(msg)
    if calls:
        await _tools.process_tool_calls(backend, calls, messages, outcome)
        return False, 0
    if text:
        cont, retries = _support.handle_direct_text_retry(
            text,
            messages,
            outcome,
            retries,
            backend.settings.max_direct_text_retries,
        )
        return not cont, retries
    return True, retries


def _chat_payload(
    backend: SGRMinimaxBackend,
    messages: list[dict[str, Any]],
    event: Any,
) -> dict[str, Any]:
    """Build the LLM chat completion request payload."""
    result: dict[str, Any] = {
        "model": backend.llm_config.model,
        "messages": messages,
        "tools": backend._openai_tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "stream": _model_routing.requires_streaming_chat(backend.llm_config.model),
        "agent_slug": backend.agent_slug,
        "request_scope": "sgr_event_tool_loop",
    }
    if backend.llm_config.temperature is not None:
        result["temperature"] = backend.llm_config.temperature
    if backend.llm_config.max_tokens is not None:
        result["max_tokens"] = backend.llm_config.max_tokens
    return result


def _build_messages(
    backend: SGRMinimaxBackend,
    session_key: str,
    peer_agent_slug: str,
    delivery: _rt.EventDelivery,
    primary_event: Any,
) -> list[dict[str, Any]]:
    """Build the initial message list for the LLM turn."""
    messages: list[dict[str, Any]] = []
    if backend.system_prompt:
        messages.append({"role": "system", "content": backend.system_prompt})
    messages.append({"role": "system", "content": _support.tool_runtime_rules_text()})
    notes = _support.operational_notes_text(peer_agent_slug=peer_agent_slug)
    if notes:
        messages.append({"role": "system", "content": notes})
    messages.extend(backend._chat_history.messages_for_session(session_key))
    messages.append(
        {
            "role": "user",
            "content": _support.wake_up_block(
                delivery=delivery,
                primary_event=primary_event,
                peer_agent_slug=peer_agent_slug,
            ),
        },
    )
    return messages
