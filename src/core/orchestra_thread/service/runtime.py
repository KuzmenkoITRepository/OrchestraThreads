"""HTTP service for OrchestraThreads backed by Postgres."""

from __future__ import annotations

import asyncio
import logging
from importlib import import_module
from typing import Any, cast

from aiohttp import ClientSession, ClientTimeout, web

from core.orchestra_thread.common import ServiceError
from core.orchestra_thread.service_runtime_config import (
    RuntimeConfigOverrides,
    load_runtime_config,
)
from core.orchestra_thread.store import ThreadStore

common = import_module("core.orchestra_thread.common")
guide = import_module("core.orchestra_thread.guide")
http_handlers = import_module("core.orchestra_thread.http_handlers")
service_event_payloads = import_module("core.orchestra_thread.service.event_payloads")
service_delivery_flow = import_module("core.orchestra_thread.service.flows.delivery_flow")
service_inactivity_flow = import_module("core.orchestra_thread.service.flows.inactivity_flow")
service_message_flow = import_module("core.orchestra_thread.service.flows.message_flow")
service_notification_flow = import_module("core.orchestra_thread.service.flows.notification_flow")
service_shared = import_module("core.orchestra_thread.service_shared")
service_thread_snapshot = import_module("core.orchestra_thread.service.thread_snapshot")
service_thread_summary = import_module("core.orchestra_thread.service.thread_summary")

logger = logging.getLogger(__name__)
SERVICE_APP_KEY: web.AppKey[OrchestraThreadsService] = web.AppKey("OrchestraThreadsService")
JsonDict = dict[str, Any]
JsonDictOrNone = JsonDict | None


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


def _json_success(payload: dict[str, Any]) -> web.Response:
    return web.json_response(payload)


def _service_error_response(exc: ServiceError) -> web.Response:
    return _json_error(exc.message, status=exc.status)


class _OrchestraThreadsServiceRuntime:  # noqa: WPS214,WPS230,WPS338 - service facade intentionally centralizes public thread API while delegating heavy logic to helper modules.
    """Thread service with retrying HTTP delivery and inactivity wakeups."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        runtime_config_overrides: RuntimeConfigOverrides | None = None,
    ) -> None:
        if db_path is not None:
            raise ValueError(
                "SQLite support has been removed. Use database_url / ORCHESTRA_THREADS_DATABASE_URL."
            )
        config = load_runtime_config(runtime_config_overrides or RuntimeConfigOverrides())
        self._apply_runtime_config(config)
        self.store = ThreadStore(
            self.database_url,
            schema_name=self.database_schema,
            min_pool_size=self.db_min_pool_size,
            max_pool_size=self.db_max_pool_size,
            command_timeout_seconds=self.db_command_timeout_seconds,
        )
        self._lock = asyncio.Lock()
        self._delivery_task: asyncio.Task[None] | None = None
        self._inactivity_task: asyncio.Task[None] | None = None
        self._http_session: ClientSession | None = None
        self.running = False

    def _apply_runtime_config(self, config: Any) -> None:
        self.database_url = config.database_url
        self.database_schema = config.database_schema
        self.db_min_pool_size = config.db_min_pool_size
        self.db_max_pool_size = config.db_max_pool_size
        self.db_command_timeout_seconds = config.db_command_timeout_seconds
        self.agent_lease_seconds = config.agent_lease_seconds
        self.delivery_poll_interval_seconds = config.delivery_poll_interval_seconds
        self.inactivity_timeout_seconds = config.inactivity_timeout_seconds
        self.retry_base_seconds = config.retry_base_seconds
        self.retry_max_seconds = config.retry_max_seconds

    async def start(self) -> None:
        if self.running:
            return
        await self.store.start()
        try:
            self._start_background_runtime()
        except Exception:
            await self.store.close()
            raise

    def _start_background_runtime(self) -> None:
        self._http_session = ClientSession(timeout=ClientTimeout(total=10))
        self.running = True
        self._delivery_task = asyncio.create_task(
            self.delivery_loop(), name="orchestra-threads-delivery"
        )
        self._inactivity_task = asyncio.create_task(
            self.inactivity_loop(), name="orchestra-threads-inactivity"
        )

    async def stop(self) -> None:
        self.running = False
        tasks = [task for task in (self._delivery_task, self._inactivity_task) if task is not None]
        for task in tasks:
            if task is not None:
                task.cancel()
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.debug("stop gather cancelled")
        self._delivery_task = None
        self._inactivity_task = None
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        await self.store.close()

    async def drop_storage(self) -> None:
        await self.store.drop_schema()

    def thread_peer_agent_slug(self, *, thread: dict[str, Any], agent_slug: str) -> str:
        participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
        participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
        if participant_a == agent_slug:
            return participant_b
        if participant_b == agent_slug:
            return participant_a
        raise common.ServiceError(
            400, f"{agent_slug} is not a participant of thread {thread.get('thread_id')}"
        )

    def validate_routing(
        self, *, thread: dict[str, Any], from_agent_slug: str, to_agent_slug: str
    ) -> None:
        thread_status = common.normalize_status(str(thread.get("status") or ""))
        if thread_status in common.THREAD_TERMINAL_STATUSES:
            raise common.ServiceError(409, f"Thread {thread.get('thread_id')} is already terminal")
        expected_peer = self.thread_peer_agent_slug(thread=thread, agent_slug=from_agent_slug)
        if expected_peer != to_agent_slug:
            raise common.ServiceError(
                400,
                f"Thread {thread.get('thread_id')} expects peer {expected_peer}, got {to_agent_slug}",
            )

    def thread_summary(self, thread: JsonDictOrNone) -> JsonDictOrNone:
        return cast(
            JsonDictOrNone,
            service_thread_summary.thread_summary(
                thread,
                agent_card_builder=self._agent_card_builder,
            ),
        )

    def _thread_summary_builder(self) -> Any:
        return service_thread_summary._ThreadSummaryBuilder(
            agent_card_builder=self._agent_card_builder,
        )

    def _build_thread_summary(self, thread: JsonDict) -> JsonDict:
        return cast(JsonDict, self.thread_summary(thread))

    def _thread_summary_from_payload(
        self,
        *,
        payload: JsonDict,
        participants: dict[str, str],
        peer_agent_slug: str,
    ) -> JsonDict:
        builder: Any = self._thread_summary_builder()
        return cast(
            JsonDict,
            builder._thread_summary_from_payload(
                payload=payload,
                participants=participants,
                peer_agent_slug=peer_agent_slug,
            ),
        )

    def _thread_participants(self, payload: JsonDict) -> dict[str, str]:
        builder: Any = self._thread_summary_builder()
        return cast(dict[str, str], builder._parts.thread_participants(payload))

    def _resolve_peer_agent_slug(
        self,
        *,
        owner_agent_slug: str,
        participant_a_agent_slug: str,
        participant_b_agent_slug: str,
    ) -> str:
        builder: Any = self._thread_summary_builder()
        return cast(
            str,
            builder._parts.resolve_peer_agent_slug(
                owner_agent_slug=owner_agent_slug,
                participant_a_agent_slug=participant_a_agent_slug,
                participant_b_agent_slug=participant_b_agent_slug,
            ),
        )

    def _thread_scope(self, payload: JsonDict) -> str:
        builder: Any = self._thread_summary_builder()
        return cast(str, builder._parts.thread_scope(payload))

    def _default_agents(
        self,
        *,
        owner_agent_slug: str,
        participant_a_agent_slug: str,
        participant_b_agent_slug: str,
        peer_agent_slug: str,
    ) -> JsonDict:
        builder: Any = self._thread_summary_builder()
        return cast(
            JsonDict,
            builder._default_agents(
                owner_agent_slug=owner_agent_slug,
                participant_a_agent_slug=participant_a_agent_slug,
                participant_b_agent_slug=participant_b_agent_slug,
                peer_agent_slug=peer_agent_slug,
            ),
        )

    def _is_terminal_status(self, status: Any) -> bool:
        builder: Any = self._thread_summary_builder()
        return cast(bool, builder._parts.is_terminal_status(status))

    def _roles_payload(
        self,
        *,
        roles: Any,
        owner_agent_slug: str,
        peer_agent_slug: str,
    ) -> Any:
        builder: Any = self._thread_summary_builder()
        return builder._parts.roles_payload(
            roles=roles,
            owner_agent_slug=owner_agent_slug,
            peer_agent_slug=peer_agent_slug,
        )

    def _pair_label(self, *, payload: JsonDict) -> Any:
        builder: Any = self._thread_summary_builder()
        return builder._parts.pair_label(payload=payload)

    def _attach_last_event(self, *, payload: JsonDict) -> None:
        self._thread_summary_builder()._attach_last_event(payload=payload)

    def thread_compact_summary(
        self,
        *,
        thread: JsonDict,
        latest_event: JsonDictOrNone,
    ) -> JsonDict:
        return cast(
            JsonDict,
            service_thread_summary.thread_compact_summary(
                thread=thread,
                latest_event=latest_event,
                agent_card_builder=self._agent_card_builder,
            ),
        )

    def _agent_card_builder(self, agent: JsonDictOrNone, agent_slug: str) -> JsonDict:
        return self.agent_card_from_record(agent, agent_slug=agent_slug)

    def agent_card_from_record(self, agent: JsonDictOrNone, *, agent_slug: str) -> JsonDict:
        context = self._agent_context(agent=agent, agent_slug=agent_slug)
        return {
            "slug": context["slug"],
            "display_name": context["display_name"],
            "agent_type": context["agent_type"],
            "backend_type": context["backend_type"],
            "active": context["online"],
            "online": context["online"],
            "metadata": context["metadata"],
            "kind": context["kind"] or None,
        }

    def _agent_context(self, *, agent: JsonDictOrNone, agent_slug: str) -> JsonDict:
        return self._agent_context_values(
            agent=agent, normalized_slug=str(agent_slug or "").strip()
        )

    def _agent_context_values(self, *, agent: JsonDictOrNone, normalized_slug: str) -> JsonDict:
        payload, metadata = self._agent_source_payload(agent)
        kind = self._metadata_kind(metadata)
        profile = self._agent_profile_values(
            agent=agent,
            payload=payload,
            metadata=metadata,
            kind=kind,
            normalized_slug=normalized_slug,
        )
        return {
            "slug": normalized_slug,
            "display_name": profile["display_name"],
            "agent_type": profile["agent_type"],
            "backend_type": profile["backend_type"],
            "online": profile["online"],
            "metadata": metadata,
            "kind": kind,
        }

    def _agent_source_payload(self, agent: JsonDictOrNone) -> tuple[JsonDict, JsonDict]:
        payload = dict(agent or {})
        return payload, self._agent_metadata(payload)

    def _metadata_kind(self, metadata: dict[str, Any]) -> str:
        return str(metadata.get("kind") or "").strip()

    def _agent_profile_values(
        self,
        *,
        agent: JsonDictOrNone,
        payload: JsonDict,
        metadata: JsonDict,
        kind: str,
        normalized_slug: str,
    ) -> JsonDict:
        return {
            "display_name": self._display_name(payload=payload, fallback=normalized_slug),
            "agent_type": self._agent_type(metadata=metadata, kind=kind),
            "backend_type": self._backend_type(metadata=metadata, kind=kind),
            "online": self._agent_online(agent=agent, payload=payload),
        }

    def _agent_metadata(self, payload: JsonDict) -> JsonDict:
        metadata = payload.get("metadata_json")
        if isinstance(metadata, dict):
            return metadata
        return {}

    def _allowed_peers(self, *, agent: JsonDictOrNone, agent_slug: str) -> set[str]:
        metadata = self._agent_context(agent=agent, agent_slug=agent_slug).get("metadata") or {}
        raw = metadata.get("allowed_peer_agent_slugs")
        if not isinstance(raw, list):
            return set()
        return {str(item).strip() for item in raw if str(item).strip()}

    def _ensure_peer_allowed(
        self,
        *,
        from_agent: JsonDictOrNone,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> None:
        allowed = self._allowed_peers(agent=from_agent, agent_slug=from_agent_slug)
        if allowed and to_agent_slug not in allowed:
            raise common.ServiceError(
                403,
                f"{from_agent_slug} is not allowed to contact {to_agent_slug}",
            )

    def _agent_online(self, *, agent: JsonDictOrNone, payload: JsonDict) -> bool:
        if not agent:
            return False
        return self._timestamp_is_online(payload)

    def _timestamp_is_online(self, payload: JsonDict) -> bool:
        return self.store.timestamp_within_lease(
            payload.get("last_seen_at"),
            lease_seconds=self.agent_lease_seconds,
        )

    def _agent_type(self, *, metadata: JsonDict, kind: str) -> str:
        agent_type = str(metadata.get("agent_type") or "").strip()
        if agent_type:
            return agent_type
        if kind == "manual-cli-agent":
            return "manual_cli"
        return "registered"

    def _backend_type(self, *, metadata: JsonDict, kind: str) -> str:
        backend_type = str(metadata.get("backend_type") or "").strip()
        if backend_type:
            return backend_type
        return kind or "unknown"

    def _display_name(self, *, payload: JsonDict, fallback: str) -> str:
        display_name = str(payload.get("display_name") or fallback).strip()
        return display_name or fallback

    def event_payload(self, event: JsonDict, *, agents_by_slug: dict[str, JsonDict]) -> JsonDict:
        return cast(
            JsonDict,
            service_event_payloads.event_payload(
                event,
                agents_by_slug=agents_by_slug,
                agent_card_builder=self._agent_card_builder,
            ),
        )

    async def agents_by_slug(self) -> dict[str, dict[str, Any]]:
        agents = await self.store.list_agents()
        return {
            str(agent.get("agent_slug") or "").strip(): agent
            for agent in agents
            if str(agent.get("agent_slug") or "").strip()
        }

    def agent_view(self, agent: dict[str, Any]) -> dict[str, Any]:
        payload = dict(agent)
        payload["online"] = self.store.timestamp_within_lease(
            agent.get("last_seen_at"),
            lease_seconds=self.agent_lease_seconds,
        )
        return payload

    async def health_snapshot(self) -> tuple[dict[str, Any], int]:
        db_ok = await self.store.ping()
        payload = {
            "status": "ok" if self.running and db_ok else "degraded",
            "service": "orchestra_threads",
            "running": self.running,
            "database": {
                "ok": db_ok,
                "schema": self.database_schema,
            },
            "time": common.utc_now_iso(),
        }
        return payload, 200 if self.running and db_ok else 503

    async def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_slug = self._required_agent_slug(payload)
        agent_payload = {
            "agent_slug": agent_slug,
            "display_name": self._display_name(payload=payload, fallback=agent_slug),
            "metadata": self._extract_metadata(payload=payload),
        }
        agent_payload.update(self._resolve_callback_urls(payload=payload))
        return await self._register_agent_record(agent_payload=agent_payload)

    def _required_agent_slug(self, payload: dict[str, Any]) -> str:
        agent_slug = str(payload.get("agent_slug") or "").strip()
        if not agent_slug:
            raise common.ServiceError(400, "agent_slug is required")
        return agent_slug

    def _resolve_callback_urls(self, *, payload: dict[str, Any]) -> dict[str, str]:
        event_callback_url = str(payload.get("event_callback_url") or "").strip()
        stop_callback_url = str(payload.get("stop_callback_url") or "").strip()
        base_url = str(payload.get("base_url") or "").strip()
        if base_url:
            normalized_base = base_url.rstrip("/")
            if not event_callback_url:
                event_callback_url = f"{normalized_base}/event"
            if not stop_callback_url:
                stop_callback_url = f"{normalized_base}/stop"
        if not event_callback_url or not stop_callback_url:
            raise common.ServiceError(400, "base_url or both callback URLs are required")
        return {
            "event_callback_url": event_callback_url,
            "stop_callback_url": stop_callback_url,
        }

    def _extract_metadata(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        metadata_raw = payload.get("metadata")
        metadata: dict[str, Any] = {}
        if isinstance(metadata_raw, dict):
            metadata = {str(key): value for key, value in metadata_raw.items()}
        return metadata

    async def _register_agent_record(self, *, agent_payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            agent = await self.store.upsert_agent(
                agent_slug=str(agent_payload["agent_slug"]),
                display_name=str(agent_payload["display_name"]),
                event_callback_url=str(agent_payload["event_callback_url"]),
                stop_callback_url=str(agent_payload["stop_callback_url"]),
                metadata=dict(agent_payload["metadata"]),
            )
        return {
            "success": True,
            "agent": self.agent_view(agent),
            "agent_lease_seconds": self.agent_lease_seconds,
        }

    async def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_slug = str(payload.get("agent_slug") or "").strip()
        if not agent_slug:
            raise common.ServiceError(400, "agent_slug is required")
        async with self._lock:
            agent = await self.store.touch_agent(agent_slug=agent_slug)
        if agent is None:
            raise common.ServiceError(404, f"Unknown agent: {agent_slug}")
        return {
            "success": True,
            "agent": self.agent_view(agent),
        }

    async def list_agents(self) -> dict[str, Any]:
        async with self._lock:
            agents = [self.agent_view(agent) for agent in await self.store.list_agents()]
        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "agent_lease_seconds": self.agent_lease_seconds,
        }

    async def get_agent_status(self, agent_slug: str) -> dict[str, Any]:
        async with self._lock:
            agent = await self.store.get_agent(agent_slug)
            if agent is None:
                raise common.ServiceError(404, f"Unknown agent: {agent_slug}")
            busy_thread = await self.store.get_agent_busy_thread(agent_slug=agent_slug)
            is_busy = busy_thread is not None
            online = self.store.timestamp_within_lease(
                agent.get("last_seen_at"),
                lease_seconds=self.agent_lease_seconds,
            )
        return {
            "success": True,
            "agent_slug": agent_slug,
            "online": online,
            "busy": is_busy,
            "status": "in_progress" if is_busy else "idle",
            "current_thread_id": self._current_thread_id(busy_thread),
        }

    def _current_thread_id(self, busy_thread: JsonDictOrNone) -> object:
        if busy_thread is None:
            return None
        return busy_thread.get("thread_id")

    async def send_message(
        self,
        *,
        request_input: Any | None = None,
        legacy_kwargs: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await service_message_flow.send_message(
                self,
                request_input=request_input,
                legacy_kwargs=legacy_kwargs,
            ),
        )

    async def _send_message_locked(self, *, request: dict[str, str | None]) -> JsonDict:
        return cast(
            JsonDict, await service_message_flow._send_message_locked(self, request=request)
        )

    async def _send_message_with_lock_context(self, message_request_context: JsonDict) -> JsonDict:
        return cast(
            JsonDict,
            await service_message_flow._send_message_with_lock_context(
                self,
                message_request_context,
            ),
        )

    async def send_notification(
        self,
        *,
        request_input: Any | None = None,
        legacy_kwargs: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await service_notification_flow.send_notification(
                self,
                request_input=request_input,
                legacy_kwargs=legacy_kwargs,
            ),
        )

    async def _send_notification_locked(self, *, request: dict[str, str]) -> JsonDict:
        return cast(
            JsonDict,
            await service_notification_flow._send_notification_locked(self, request=request),
        )

    async def _send_notification_with_lock_context(
        self, notification_context: JsonDict
    ) -> JsonDict:
        return cast(
            JsonDict,
            await service_notification_flow._send_notification_with_lock_context(
                self,
                notification_context,
            ),
        )

    async def list_threads(self, *, scope: str, limit: int) -> dict[str, Any]:
        normalized_scope = str(scope or "active").strip().lower()
        if normalized_scope not in {"active", "all"}:
            raise common.ServiceError(400, "scope must be active or all")
        async with self._lock:
            agents_by_slug = await self.agents_by_slug()
            threads = [
                self.thread_summary(
                    self.inject_agent_cards(thread=thread, agents_by_slug=agents_by_slug)
                )
                for thread in await self.store.list_threads(
                    active_only=normalized_scope == "active", limit=max(1, limit)
                )
            ]
        return {
            "success": True,
            "scope": normalized_scope,
            "threads": threads,
        }

    async def get_thread(self, *, thread_id: str, limit: int) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            raise common.ServiceError(400, "thread_id is required")
        snapshot = await self._thread_snapshot(thread_id=normalized_thread_id, limit=limit)
        agents_by_slug = snapshot["agents_by_slug"]
        events = [
            self.event_payload(event, agents_by_slug=agents_by_slug)
            for event in snapshot["raw_events"]
        ]
        related = self._related_threads(snapshot=snapshot)
        return {
            "success": True,
            "thread": self.thread_summary(
                self.inject_agent_cards(
                    thread=related["thread"],
                    agents_by_slug=agents_by_slug,
                )
            ),
            "events": events,
            "related": {
                "parent_thread": self.thread_summary(
                    self.inject_agent_cards(
                        thread=related["parent_thread"],
                        agents_by_slug=agents_by_slug,
                    )
                ),
                "root_thread": self.thread_summary(
                    self.inject_agent_cards(
                        thread=related["root_thread"],
                        agents_by_slug=agents_by_slug,
                    )
                ),
                "child_threads": [
                    self.thread_summary(
                        self.inject_agent_cards(
                            thread=item,
                            agents_by_slug=agents_by_slug,
                        )
                    )
                    for item in related["child_threads"]
                ],
                "root_group": [
                    self.thread_summary(
                        self.inject_agent_cards(
                            thread=item,
                            agents_by_slug=snapshot["agents_by_slug"],
                        )
                    )
                    for item in snapshot["root_group"]
                ],
            },
        }

    async def _thread_snapshot(self, *, thread_id: str, limit: int) -> dict[str, Any]:
        thread_limit = max(1, limit)
        async with self._lock:
            agents_by_slug = await self.agents_by_slug()
            thread = await self.store.get_thread(thread_id)
            if thread is None:
                raise common.ServiceError(404, f"Unknown thread_id: {thread_id}")
            raw_events = await self.store.list_thread_events(
                thread_id=thread_id, limit=thread_limit
            )
            root_group = await self.store.list_threads_by_root(
                root_thread_id=str(thread.get("root_thread_id"))
            )
        return {
            "agents_by_slug": agents_by_slug,
            "thread": thread,
            "raw_events": raw_events,
            "root_group": root_group,
            "thread_id": thread_id,
        }

    def _related_threads(self, *, snapshot: JsonDict) -> JsonDict:
        return cast(JsonDict, service_thread_snapshot._related_threads(snapshot=snapshot))

    def inject_agent_cards(
        self,
        *,
        thread: JsonDictOrNone,
        agents_by_slug: dict[str, JsonDict],
    ) -> JsonDictOrNone:
        if thread is None:
            return None
        payload, roles, cards = self._inject_agent_parts(
            thread=thread, agents_by_slug=agents_by_slug
        )
        pair_label = self._inject_pair_label(cards)
        payload["agents"] = cards
        payload["roles"] = roles
        payload["pair_label"] = pair_label
        return payload

    def _inject_agent_parts(
        self,
        *,
        thread: JsonDict,
        agents_by_slug: dict[str, JsonDict],
    ) -> tuple[JsonDict, JsonDict, JsonDict]:
        return self._inject_agent_parts_values(thread=thread, agents_by_slug=agents_by_slug)

    def _inject_agent_parts_values(
        self,
        *,
        thread: JsonDict,
        agents_by_slug: dict[str, JsonDict],
    ) -> tuple[JsonDict, JsonDict, JsonDict]:
        return self._assemble_injected_agent_parts(thread=thread, agents_by_slug=agents_by_slug)

    def _assemble_injected_agent_parts(
        self,
        *,
        thread: JsonDict,
        agents_by_slug: dict[str, JsonDict],
    ) -> tuple[JsonDict, JsonDict, JsonDict]:
        payload, participants, peer_agent_slug = self._inject_agent_context(thread)
        slugs = self._participant_slugs_dict(participants)
        return (
            payload,
            self._inject_roles(owner_agent_slug=slugs["owner"], peer_agent_slug=peer_agent_slug),
            self._inject_cards(
                agents_by_slug=agents_by_slug,
                owner_agent_slug=slugs["owner"],
                participant_a_agent_slug=slugs["participant_a"],
                participant_b_agent_slug=slugs["participant_b"],
                peer_agent_slug=peer_agent_slug,
            ),
        )

    def _participant_slugs_dict(self, participants: dict[str, str]) -> dict[str, str]:
        owner_agent_slug, participant_a_agent_slug, participant_b_agent_slug = (
            self._participant_slugs(participants)
        )
        return {
            "owner": owner_agent_slug,
            "participant_a": participant_a_agent_slug,
            "participant_b": participant_b_agent_slug,
        }

    def _inject_cards(
        self,
        *,
        agents_by_slug: dict[str, JsonDict],
        owner_agent_slug: str,
        participant_a_agent_slug: str,
        participant_b_agent_slug: str,
        peer_agent_slug: str,
    ) -> JsonDict:
        return {
            "owner": self.agent_card_from_record(
                agents_by_slug.get(owner_agent_slug),
                agent_slug=owner_agent_slug,
            ),
            "participant_a": self.agent_card_from_record(
                agents_by_slug.get(participant_a_agent_slug),
                agent_slug=participant_a_agent_slug,
            ),
            "participant_b": self.agent_card_from_record(
                agents_by_slug.get(participant_b_agent_slug),
                agent_slug=participant_b_agent_slug,
            ),
            "peer": self.agent_card_from_record(
                agents_by_slug.get(peer_agent_slug),
                agent_slug=peer_agent_slug,
            ),
        }

    def _inject_roles(self, *, owner_agent_slug: str, peer_agent_slug: str) -> JsonDict:
        return {
            "owner_agent_slug": owner_agent_slug,
            "peer_agent_slug": peer_agent_slug,
        }

    def _inject_pair_label(self, cards: JsonDict) -> str:
        return (
            f"{cards['participant_a']['display_name']} <-> {cards['participant_b']['display_name']}"
        )

    def _inject_agent_context(
        self,
        thread: JsonDict,
    ) -> tuple[JsonDict, dict[str, str], str]:
        payload = dict(thread)
        participants, peer_agent_slug = self._inject_agent_participants(payload)
        return payload, participants, peer_agent_slug

    def _participant_slugs(self, participants: dict[str, str]) -> tuple[str, str, str]:
        return (
            participants["owner"],
            participants["participant_a"],
            participants["participant_b"],
        )

    def _inject_agent_participants(
        self,
        payload: JsonDict,
    ) -> tuple[dict[str, str], str]:
        participants = self._thread_participants(payload)
        return (
            participants,
            self._resolve_peer_agent_slug(
                owner_agent_slug=participants["owner"],
                participant_a_agent_slug=participants["participant_a"],
                participant_b_agent_slug=participants["participant_b"],
            ),
        )

    async def get_thread_compact(self, *, thread_id: str) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            raise common.ServiceError(400, "thread_id is required")
        async with self._lock:
            thread = await self.store.get_thread(normalized_thread_id)
            if thread is None:
                raise common.ServiceError(404, f"Unknown thread_id: {normalized_thread_id}")
            latest_event = await self.store.get_latest_thread_event(thread_id=normalized_thread_id)
        return {
            "success": True,
            "thread": self.thread_compact_summary(thread=thread, latest_event=latest_event),
        }

    async def get_instruction(self, *, view: str, section: str | None) -> dict[str, Any]:
        try:
            instruction = guide.build_instruction_payload(view=view, section=section)
        except ValueError as exc:
            raise common.ServiceError(400, str(exc)) from exc
        return {
            "success": True,
            "instruction": instruction,
        }

    async def notify_stop(self, *, agent_slug: str, payload: dict[str, Any]) -> None:
        session = self._http_session
        if session is None:
            return
        async with self._lock:
            agent = await self.store.get_agent(agent_slug)
        if agent is None:
            return
        if not self.store.timestamp_within_lease(
            agent.get("last_seen_at"), lease_seconds=self.agent_lease_seconds
        ):
            return
        stop_callback_url = str(agent.get("stop_callback_url") or "").strip()
        if not stop_callback_url:
            return
        try:
            async with session.post(stop_callback_url, json=payload) as response:
                if response.status >= 400:
                    logger.warning("stop callback failed for %s: %s", agent_slug, response.status)
        except Exception as exc:
            logger.warning("stop callback failed for %s: %s", agent_slug, exc)

    async def delivery_loop(self) -> None:
        while self.running:
            try:
                await service_delivery_flow._process_pending_events(self)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("delivery loop error: %s", exc, exc_info=True)
            await asyncio.sleep(self.delivery_poll_interval_seconds)

    async def _process_pending_events(self) -> None:
        await service_delivery_flow._process_pending_events(self)

    async def _deliver_pending_event(
        self,
        *,
        item: dict[str, Any],
        callback_url: str,
        event_id: str,
    ) -> None:
        await service_delivery_flow._deliver_pending_event(
            self,
            item=item,
            callback_url=callback_url,
            event_id=event_id,
        )

    async def _post_delivery(self, *, callback_url: str, payload: dict[str, Any]) -> None:
        await service_delivery_flow._post_delivery(
            self,
            callback_url=callback_url,
            payload=payload,
        )

    async def _mark_delivery_failed(self, *, event_id: str, error_text: str) -> None:
        await service_delivery_flow._mark_delivery_failed(
            self,
            event_id=event_id,
            error_text=error_text,
        )

    async def inactivity_loop(self) -> None:
        poll_interval = max(1.0, self.inactivity_timeout_seconds / 4.0)
        while self.running:
            try:
                await service_inactivity_flow._process_inactivity_candidates(self)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("inactivity loop error: %s", exc, exc_info=True)
            await asyncio.sleep(poll_interval)

    async def _process_inactivity_candidates(self) -> None:
        await service_inactivity_flow._process_inactivity_candidates(self)

    async def _build_inactivity_task(self, *, thread: dict[str, Any]) -> None:
        await service_inactivity_flow._build_inactivity_task(self, thread=thread)

    async def _append_inactivity_event(
        self,
        *,
        thread_id: str,
        recipient: str,
        message: str,
    ) -> None:
        await service_inactivity_flow._append_inactivity_event(
            self,
            thread_id=thread_id,
            recipient=recipient,
            message=message,
        )


OrchestraThreadsService = _OrchestraThreadsServiceRuntime


def build_app(service: OrchestraThreadsService) -> web.Application:
    app = web.Application()
    handlers = http_handlers.HttpHandlers(service)
    app[SERVICE_APP_KEY] = service
    _register_routes(app=app, handlers=handlers)
    if service_shared.STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(service_shared.STATIC_DIR), show_index=False)
    return app


def _register_routes(*, app: web.Application, handlers: Any) -> None:
    route_specs: tuple[tuple[str, str, Any], ...] = (
        ("get", "/", handlers.handle_ui),
        ("get", "/ui", handlers.handle_ui),
        ("get", "/healthz", handlers.handle_health),
        ("post", "/agents/register", handlers.handle_register),
        ("post", "/agents/heartbeat", handlers.handle_heartbeat),
        ("get", "/agents", handlers.handle_agents),
        ("get", "/agents/{agent_slug}/status", handlers.handle_agent_status),
        ("get", "/api/v1/instructions", handlers.handle_instructions),
        ("post", "/api/v1/messages", handlers.handle_messages),
        ("post", "/api/v1/notifications", handlers.handle_notifications),
        ("get", "/api/v1/threads", handlers.handle_threads),
        ("get", "/api/v1/threads/{thread_id}/compact", handlers.handle_thread_compact),
        ("get", "/api/v1/threads/{thread_id}", handlers.handle_thread),
    )
    for method, path, handler in route_specs:
        getattr(app.router, f"add_{method}")(path, handler)
