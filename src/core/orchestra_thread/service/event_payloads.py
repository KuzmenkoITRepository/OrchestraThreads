from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.orchestra_thread.service_shared import message_preview

JsonDict = dict[str, Any]
JsonDictOrNone = JsonDict | None
AgentCardBuilder = Callable[[JsonDictOrNone, str], JsonDict]


def event_payload(
    event: JsonDict,
    *,
    agents_by_slug: dict[str, JsonDict],
    agent_card_builder: AgentCardBuilder,
) -> JsonDict:
    return _EventPayloadBuilder(
        agents_by_slug=agents_by_slug,
        agent_card_builder=agent_card_builder,
    ).event_payload(event)


class _EventPayloadBuilder:
    def __init__(
        self,
        *,
        agents_by_slug: dict[str, JsonDict],
        agent_card_builder: AgentCardBuilder,
    ) -> None:
        self._agents_by_slug = agents_by_slug
        self._agent_card_builder = agent_card_builder

    def event_payload(self, event: JsonDict) -> JsonDict:
        event_context = self._event_context(event)
        return {
            "event_id": event.get("event_id"),
            "sequence_no": event.get("sequence_no"),
            "event_kind": event.get("event_kind"),
            "notification_status": event.get("notification_status"),
            "from_agent_slug": event_context["from_slug"],
            "to_agent_slug": event_context["to_slug"],
            "from_agent": event_context["from_agent"],
            "to_agent": event_context["to_agent"],
            "requires_action": event_context["requires_action"],
            "interrupts_runtime": event_context["interrupts_runtime"],
            "requires_response": event_context["requires_response"],
            "pending_delivery": bool(event.get("pending_delivery")),
            "delivery_attempt_count": int(event.get("delivery_attempt_count") or 0),
            "last_delivery_error": event.get("last_delivery_error"),
            "created_at": event.get("created_at"),
            "message_text": event_context["message_text"],
            "message_preview": message_preview(str(event_context["message_text"])),
        }

    def _event_context(self, event: JsonDict) -> JsonDict:
        slugs = self._event_slugs(event)
        event_flags = self._event_flags(event)
        from_agent, to_agent = self._event_agents(slugs=slugs)
        requires_action = self._requires_action(event_flags)
        return {
            "message_text": str(event.get("message_text") or ""),
            "from_slug": slugs["from"],
            "to_slug": slugs["to"],
            "from_agent": from_agent,
            "to_agent": to_agent,
            "requires_action": requires_action,
            "interrupts_runtime": event_flags["interrupts_runtime"],
            "requires_response": event_flags["requires_response"],
        }

    def _event_agents(self, *, slugs: dict[str, str]) -> tuple[JsonDict, JsonDict]:
        from_slug = slugs["from"]
        to_slug = slugs["to"]
        return (
            self._agent_card_builder(self._agents_by_slug.get(from_slug), from_slug),
            self._agent_card_builder(self._agents_by_slug.get(to_slug), to_slug),
        )

    def _requires_action(self, event_flags: dict[str, bool]) -> bool:
        return event_flags["interrupts_runtime"] or event_flags["requires_response"]

    def _event_slugs(self, event: JsonDict) -> dict[str, str]:
        return {
            "from": str(event.get("from_agent_slug") or "").strip(),
            "to": str(event.get("to_agent_slug") or "").strip(),
        }

    def _event_flags(self, event: JsonDict) -> dict[str, bool]:
        requires_response = bool(event.get("requires_response"))
        interrupts_runtime = bool(event.get("interrupts_runtime"))
        return {
            "requires_response": requires_response,
            "interrupts_runtime": interrupts_runtime,
        }
