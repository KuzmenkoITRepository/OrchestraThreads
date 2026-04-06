"""SGR turn execution — LLM loop and message building."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from agents.sgr.agent_runtime import support as _support
from agents.sgr.agent_runtime import tool_exec as _tools
from core.orchestra_agents import runtime as _rt
from core.orchestra_thread import active_context as _active_ctx

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.backend import SGRMinimaxBackend


async def run_turn(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    primary_event: Any,
    thread_summary: dict[str, Any],
    peer_agent_slug: str,
) -> _support.AgentTurnOutcome:
    """Execute the full LLM tool loop for one event."""
    messages = _build_messages(backend, thread_summary, peer_agent_slug, delivery, primary_event)
    outcome = _support.AgentTurnOutcome()
    retries = 0
    with _active_context_scope(backend, primary_event, thread_summary, peer_agent_slug):
        step = 0
        while step < backend.settings.max_reasoning_steps:
            step += 1
            should_stop, retries = await _run_step(
                backend, messages, outcome, retries, primary_event
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
    result: dict[str, Any] = {
        "model": backend.llm_config.model,
        "messages": messages,
        "tools": backend._openai_tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "stream": False,
        "agent_slug": backend.agent_slug,
        "thread_id": event.thread_id,
        "root_thread_id": event.root_thread_id,
        "parent_thread_id": event.parent_thread_id,
        "request_scope": "orchestra_thread_tool_loop",
    }
    if backend.llm_config.temperature is not None:
        result["temperature"] = backend.llm_config.temperature
    if backend.llm_config.max_tokens is not None:
        result["max_tokens"] = backend.llm_config.max_tokens
    return result


def _build_messages(
    backend: SGRMinimaxBackend,
    thread_summary: dict[str, Any],
    peer_agent_slug: str,
    delivery: _rt.EventDelivery,
    primary_event: Any,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if backend.system_prompt:
        messages.append({"role": "system", "content": backend.system_prompt})
    messages.append({"role": "system", "content": _support.tool_runtime_rules_text()})
    notes = _support.operational_notes_text(
        backend._thread_ops.guide_text,
        thread_summary=thread_summary,
        peer_agent_slug=peer_agent_slug,
    )
    if notes:
        messages.append({"role": "system", "content": notes})
    messages.append(
        {
            "role": "user",
            "content": _support.wake_up_block(
                delivery=delivery,
                primary_event=primary_event,
                thread_summary=thread_summary,
                peer_agent_slug=peer_agent_slug,
            ),
        }
    )
    return messages


@contextmanager
def _active_context_scope(
    backend: SGRMinimaxBackend,
    event: Any,
    thread_summary: dict[str, Any],
    peer_agent_slug: str,
) -> Iterator[None]:
    payload = {
        "agent_slug": backend.agent_slug,
        "thread_id": event.thread_id,
        "root_thread_id": event.root_thread_id or thread_summary.get("root_thread_id"),
        "parent_thread_id": event.parent_thread_id or thread_summary.get("parent_thread_id"),
        "source_agent_slug": peer_agent_slug,
        "target_agent_slug": backend.agent_slug,
        "owner_agent_slug": thread_summary.get("owner_agent_slug"),
        "current_mode": "reply",
    }
    _active_ctx.write_active_context(payload)
    try:
        yield
    finally:
        _active_ctx.clear_active_context()
