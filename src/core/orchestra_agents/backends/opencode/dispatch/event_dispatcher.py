"""Convert agent events into opencode prompts and dispatch them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.orchestra_agents.runtime import AgentEvent

if TYPE_CHECKING:
    from core.orchestra_agents.backends.opencode.process.client import OpencodeClient
    from core.orchestra_agents.backends.opencode.process.session_manager import (
        SessionManager,
    )


class EventDispatcher:
    def __init__(self, client: OpencodeClient, session_manager: SessionManager) -> None:
        self._client = client
        self._session_manager = session_manager

    def format_prompt(self, event: AgentEvent) -> str:
        event_kind = event.event_kind
        from_agent_slug = event.from_agent_slug or "unknown"
        thread_id = event.thread_id or "n/a"
        return (
            f"[Thread Event: {event_kind}]\n"
            f"From: {from_agent_slug}\n"
            f"Thread: {thread_id}\n\n"
            f"{event.message_text}"
        )

    async def dispatch_event(
        self,
        event: AgentEvent,
        context_id: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        session_id = await self._session_manager.get_or_create_session(context_id)
        prompt = self.format_prompt(event)
        response = await self._client.send_message(session_id, prompt, timeout=timeout)
        payload = dict(response)
        payload["opencode_session_id"] = session_id
        return payload
