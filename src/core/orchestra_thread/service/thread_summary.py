from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.orchestra_thread import common
from core.orchestra_thread.service_shared import message_preview

JsonDict = dict[str, Any]
JsonDictOrNone = JsonDict | None
AgentCardBuilder = Callable[[JsonDictOrNone, str], JsonDict]


def thread_summary(
    thread: JsonDictOrNone,
    *,
    agent_card_builder: AgentCardBuilder,
) -> JsonDictOrNone:
    if thread is None:
        return None
    return _ThreadSummaryBuilder(agent_card_builder=agent_card_builder).thread_summary(thread)


def thread_compact_summary(
    *,
    thread: JsonDict,
    latest_event: JsonDictOrNone,
    agent_card_builder: AgentCardBuilder,
) -> JsonDict:
    return _ThreadSummaryBuilder(
        agent_card_builder=agent_card_builder,
    ).thread_compact_summary(thread=thread, latest_event=latest_event)


class _ThreadSummaryBuilder:
    def __init__(self, *, agent_card_builder: AgentCardBuilder) -> None:
        self._agent_card_builder = agent_card_builder
        self._parts = _ThreadSummaryParts()

    def thread_summary(self, thread: JsonDict) -> JsonDict:
        payload = dict(thread)
        participants = self._parts.thread_participants(payload)
        peer_agent_slug = self._parts.resolve_peer_agent_slug(
            owner_agent_slug=participants["owner"],
            participant_a_agent_slug=participants["participant_a"],
            participant_b_agent_slug=participants["participant_b"],
        )
        return self._thread_summary_from_payload(
            payload=payload,
            participants=participants,
            peer_agent_slug=peer_agent_slug,
        )

    def thread_compact_summary(
        self,
        *,
        thread: JsonDict,
        latest_event: JsonDictOrNone,
    ) -> JsonDict:
        payload = self.thread_summary(thread)
        latest = latest_event or {}
        payload["last_event_kind"] = latest.get("event_kind")
        payload["last_event_notification_status"] = latest.get("notification_status")
        payload["last_event_from_agent_slug"] = latest.get("from_agent_slug")
        payload["last_event_to_agent_slug"] = latest.get("to_agent_slug")
        payload["last_event_created_at"] = latest.get("created_at")
        payload["last_event_message_preview"] = message_preview(
            str(latest.get("message_text") or "")
        )
        return payload

    def _thread_summary_from_payload(
        self,
        *,
        payload: JsonDict,
        participants: dict[str, str],
        peer_agent_slug: str,
    ) -> JsonDict:
        thread_scope = self._parts.thread_scope(payload)
        agents = payload.get("agents")
        if not isinstance(agents, dict):
            agents = self._default_agents(
                owner_agent_slug=participants["owner"],
                participant_a_agent_slug=participants["participant_a"],
                participant_b_agent_slug=participants["participant_b"],
                peer_agent_slug=peer_agent_slug,
            )
        payload["is_terminal"] = self._parts.is_terminal_status(payload.get("status"))
        payload["scope"] = thread_scope
        payload["thread_scope"] = thread_scope
        payload["agents"] = agents
        payload["roles"] = self._parts.roles_payload(
            roles=payload.get("roles"),
            owner_agent_slug=participants["owner"],
            peer_agent_slug=peer_agent_slug,
        )
        payload["pair_label"] = self._parts.pair_label(payload=payload)
        self._attach_last_event(payload=payload)
        return payload

    def _default_agents(
        self,
        *,
        owner_agent_slug: str,
        participant_a_agent_slug: str,
        participant_b_agent_slug: str,
        peer_agent_slug: str,
    ) -> JsonDict:
        return {
            "owner": self._agent_card_builder(None, owner_agent_slug),
            "participant_a": self._agent_card_builder(None, participant_a_agent_slug),
            "participant_b": self._agent_card_builder(None, participant_b_agent_slug),
            "peer": self._agent_card_builder(None, peer_agent_slug),
        }

    def _attach_last_event(self, *, payload: JsonDict) -> None:
        last_event_message_text = str(payload.get("last_event_message_text") or "")
        payload["last_event"] = None
        if payload.get("last_event_id"):
            payload["last_event"] = {
                "event_id": payload.get("last_event_id"),
                "sequence_no": payload.get("last_event_sequence_no"),
                "event_kind": payload.get("last_event_kind"),
                "notification_status": payload.get("last_event_notification_status"),
                "from_agent_slug": payload.get("last_event_from_agent_slug"),
                "to_agent_slug": payload.get("last_event_to_agent_slug"),
                "created_at": payload.get("last_event_created_at"),
                "pending_delivery": payload.get("last_event_pending_delivery"),
                "message_preview": message_preview(last_event_message_text),
            }


class _ThreadSummaryParts:
    def thread_participants(self, payload: JsonDict) -> dict[str, str]:
        return {
            "owner": str(payload.get("owner_agent_slug") or "").strip(),
            "participant_a": str(payload.get("participant_a_agent_slug") or "").strip(),
            "participant_b": str(payload.get("participant_b_agent_slug") or "").strip(),
        }

    def resolve_peer_agent_slug(
        self,
        *,
        owner_agent_slug: str,
        participant_a_agent_slug: str,
        participant_b_agent_slug: str,
    ) -> str:
        if owner_agent_slug == participant_a_agent_slug:
            return participant_b_agent_slug
        if owner_agent_slug and owner_agent_slug == participant_b_agent_slug:
            return participant_a_agent_slug
        return participant_a_agent_slug

    def thread_scope(self, payload: JsonDict) -> str:
        if payload.get("thread_id") == payload.get("root_thread_id"):
            return "root"
        return "child"

    def is_terminal_status(self, status: Any) -> bool:
        return common.normalize_status(str(status or "")) in common.THREAD_TERMINAL_STATUSES

    def roles_payload(self, *, roles: Any, owner_agent_slug: str, peer_agent_slug: str) -> Any:
        if roles:
            return roles
        return {
            "owner_agent_slug": owner_agent_slug,
            "peer_agent_slug": peer_agent_slug,
        }

    def pair_label(self, *, payload: JsonDict) -> Any:
        pair_label = payload.get("pair_label")
        if pair_label:
            return pair_label
        return (
            f"{payload['agents']['participant_a']['display_name']} "
            f"<-> {payload['agents']['participant_b']['display_name']}"
        )
