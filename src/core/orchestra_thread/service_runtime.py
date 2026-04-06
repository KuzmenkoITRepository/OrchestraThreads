"""HTTP service for OrchestraThreads backed by Postgres."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from aiohttp import ClientSession, ClientTimeout, web

from core.orchestra_thread import common, guide, http_handlers, service_shared
from core.orchestra_thread.store import ThreadStore
from core.orchestra_thread.store_thread_creation import ChildThreadRequest, RootThreadRequest
from core.orchestra_thread.store_thread_events import AppendEventRequest

logger = logging.getLogger(__name__)
SERVICE_APP_KEY: web.AppKey[OrchestraThreadsService] = web.AppKey("OrchestraThreadsService")
JsonDict = dict[str, Any]
JsonDictOrNone = JsonDict | None


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


def _json_success(payload: dict[str, Any]) -> web.Response:
    return web.json_response(payload)


def _service_error_response(exc: common.ServiceError) -> web.Response:
    return _json_error(exc.message, status=exc.status)


def message_preview(text: str, *, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


class OrchestraThreadsService:  # noqa: WPS214,WPS230,WPS338
    """Thread service with retrying HTTP delivery and inactivity wakeups."""

    def __init__(  # noqa: WPS211
        self,
        *,
        database_url: str | None = None,
        database_schema: str | None = None,
        db_min_pool_size: int | None = None,
        db_max_pool_size: int | None = None,
        db_command_timeout_seconds: float | None = None,
        db_path: str | None = None,
        agent_lease_seconds: int | None = None,
        delivery_poll_interval_seconds: float | None = None,
        inactivity_timeout_seconds: int | None = None,
        retry_base_seconds: int | None = None,
        retry_max_seconds: int | None = None,
    ) -> None:
        if db_path is not None:
            raise ValueError(
                "SQLite support has been removed. Use database_url / ORCHESTRA_THREADS_DATABASE_URL."
            )
        self._load_runtime_config(
            database_url=database_url,
            database_schema=database_schema,
            db_min_pool_size=db_min_pool_size,
            db_max_pool_size=db_max_pool_size,
            db_command_timeout_seconds=db_command_timeout_seconds,
            agent_lease_seconds=agent_lease_seconds,
            delivery_poll_interval_seconds=delivery_poll_interval_seconds,
            inactivity_timeout_seconds=inactivity_timeout_seconds,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )
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

    def _load_runtime_config(  # noqa: WPS211
        self,
        *,
        database_url: str | None,
        database_schema: str | None,
        db_min_pool_size: int | None,
        db_max_pool_size: int | None,
        db_command_timeout_seconds: float | None,
        agent_lease_seconds: int | None,
        delivery_poll_interval_seconds: float | None,
        inactivity_timeout_seconds: int | None,
        retry_base_seconds: int | None,
        retry_max_seconds: int | None,
    ) -> None:
        self.database_url = str(
            database_url
            or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
            or "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads"
        ).strip()
        self.database_schema = self._schema_value(database_schema)
        self.db_min_pool_size = self._int_setting(
            explicit_value=db_min_pool_size,
            env_name="ORCHESTRA_THREADS_DB_MIN_POOL_SIZE",
            default="5",
            minimum=1,
        )
        self.db_max_pool_size = self._int_setting(
            explicit_value=db_max_pool_size,
            env_name="ORCHESTRA_THREADS_DB_MAX_POOL_SIZE",
            default="20",
            minimum=self.db_min_pool_size,
        )
        self.db_command_timeout_seconds = self._float_setting(
            explicit_value=db_command_timeout_seconds,
            env_name="ORCHESTRA_THREADS_DB_COMMAND_TIMEOUT_SECONDS",
            default="10",
            minimum=1.0,
        )
        self.agent_lease_seconds = self._int_setting(
            explicit_value=agent_lease_seconds,
            env_name="ORCHESTRA_THREADS_AGENT_LEASE_SECONDS",
            default="30",
            minimum=5,
        )
        self.delivery_poll_interval_seconds = self._float_setting(
            explicit_value=delivery_poll_interval_seconds,
            env_name="ORCHESTRA_THREADS_DELIVERY_POLL_INTERVAL_SECONDS",
            default="1",
            minimum=0.2,
        )
        self.inactivity_timeout_seconds = self._int_setting(
            explicit_value=inactivity_timeout_seconds,
            env_name="ORCHESTRA_THREADS_INACTIVITY_TIMEOUT_SECONDS",
            default="60",
            minimum=10,
        )
        self.retry_base_seconds = self._int_setting(
            explicit_value=retry_base_seconds,
            env_name="ORCHESTRA_THREADS_RETRY_BASE_SECONDS",
            default="2",
            minimum=1,
        )
        self.retry_max_seconds = self._int_setting(
            explicit_value=retry_max_seconds,
            env_name="ORCHESTRA_THREADS_RETRY_MAX_SECONDS",
            default="30",
            minimum=self.retry_base_seconds,
        )

    def _schema_value(self, database_schema: str | None) -> str:
        value = str(database_schema or os.getenv("ORCHESTRA_THREADS_DB_SCHEMA") or "public").strip()
        return value or "public"

    def _int_setting(
        self,
        *,
        explicit_value: int | None,
        env_name: str,
        default: str,
        minimum: int,
    ) -> int:
        raw_value = explicit_value or os.getenv(env_name) or default
        return max(minimum, int(raw_value))

    def _float_setting(
        self,
        *,
        explicit_value: float | None,
        env_name: str,
        default: str,
        minimum: float,
    ) -> float:
        raw_value = explicit_value or os.getenv(env_name) or default
        return max(minimum, float(raw_value))

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
        if thread is None:
            return None
        return self._build_thread_summary(thread)

    def _build_thread_summary(self, thread: JsonDict) -> JsonDict:
        payload = dict(thread)
        participants = self._thread_participants(payload)
        peer_agent_slug = self._resolve_peer_agent_slug(
            owner_agent_slug=participants["owner"],
            participant_a_agent_slug=participants["participant_a"],
            participant_b_agent_slug=participants["participant_b"],
        )
        return self._thread_summary_from_payload(
            payload=payload,
            participants=participants,
            peer_agent_slug=peer_agent_slug,
        )

    def _thread_summary_from_payload(
        self,
        *,
        payload: JsonDict,
        participants: dict[str, str],
        peer_agent_slug: str,
    ) -> JsonDict:
        thread_scope = self._thread_scope(payload)
        agents = payload.get("agents")
        if not isinstance(agents, dict):
            agents = self._default_agents(
                owner_agent_slug=participants["owner"],
                participant_a_agent_slug=participants["participant_a"],
                participant_b_agent_slug=participants["participant_b"],
                peer_agent_slug=peer_agent_slug,
            )
        payload["is_terminal"] = self._is_terminal_status(payload.get("status"))
        payload["scope"] = thread_scope
        payload["thread_scope"] = thread_scope
        payload["agents"] = agents
        payload["roles"] = self._roles_payload(
            roles=payload.get("roles"),
            owner_agent_slug=participants["owner"],
            peer_agent_slug=peer_agent_slug,
        )
        payload["pair_label"] = self._pair_label(payload=payload)
        self._attach_last_event(payload=payload)
        return payload

    def _thread_participants(self, payload: JsonDict) -> dict[str, str]:
        return {
            "owner": str(payload.get("owner_agent_slug") or "").strip(),
            "participant_a": str(payload.get("participant_a_agent_slug") or "").strip(),
            "participant_b": str(payload.get("participant_b_agent_slug") or "").strip(),
        }

    def _resolve_peer_agent_slug(
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

    def _thread_scope(self, payload: JsonDict) -> str:
        if payload.get("thread_id") == payload.get("root_thread_id"):
            return "root"
        return "child"

    def _default_agents(
        self,
        *,
        owner_agent_slug: str,
        participant_a_agent_slug: str,
        participant_b_agent_slug: str,
        peer_agent_slug: str,
    ) -> JsonDict:
        return {
            "owner": self.agent_card_from_record(None, agent_slug=owner_agent_slug),
            "participant_a": self.agent_card_from_record(None, agent_slug=participant_a_agent_slug),
            "participant_b": self.agent_card_from_record(None, agent_slug=participant_b_agent_slug),
            "peer": self.agent_card_from_record(None, agent_slug=peer_agent_slug),
        }

    def _is_terminal_status(self, status: Any) -> bool:
        return common.normalize_status(str(status or "")) in common.THREAD_TERMINAL_STATUSES

    def _roles_payload(
        self,
        *,
        roles: Any,
        owner_agent_slug: str,
        peer_agent_slug: str,
    ) -> Any:
        if roles:
            return roles
        return {
            "owner_agent_slug": owner_agent_slug,
            "peer_agent_slug": peer_agent_slug,
        }

    def _pair_label(self, *, payload: JsonDict) -> Any:
        pair_label = payload.get("pair_label")
        if pair_label:
            return pair_label
        return (
            f"{payload['agents']['participant_a']['display_name']} "
            f"<-> {payload['agents']['participant_b']['display_name']}"
        )

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

    def thread_compact_summary(
        self,
        *,
        thread: JsonDict,
        latest_event: JsonDictOrNone,
    ) -> JsonDict:
        payload = self.thread_summary(thread) or {}
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
        event_context = self._event_context(event=event, agents_by_slug=agents_by_slug)
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

    def _event_context(
        self,
        *,
        event: JsonDict,
        agents_by_slug: dict[str, JsonDict],
    ) -> JsonDict:
        slugs = self._event_slugs(event)
        event_flags = self._event_flags(event)
        from_agent, to_agent = self._event_agents(slugs=slugs, agents_by_slug=agents_by_slug)
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

    def _event_agents(
        self,
        *,
        slugs: dict[str, str],
        agents_by_slug: dict[str, JsonDict],
    ) -> tuple[JsonDict, JsonDict]:
        from_slug = slugs["from"]
        to_slug = slugs["to"]
        return (
            self.agent_card_from_record(agents_by_slug.get(from_slug), agent_slug=from_slug),
            self.agent_card_from_record(agents_by_slug.get(to_slug), agent_slug=to_slug),
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

    async def send_message(  # noqa: WPS211
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        thread_id: str | None,
        parent_thread_id: str | None,
        client_request_id: str,
    ) -> dict[str, Any]:
        request = self._message_request(
            from_agent_slug=from_agent_slug,
            to_agent_slug=to_agent_slug,
            message_text=message_text,
            thread_id=thread_id,
            parent_thread_id=parent_thread_id,
            client_request_id=client_request_id,
        )
        return await self._send_message_locked(request=request)

    def _message_request(  # noqa: WPS211
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        thread_id: str | None,
        parent_thread_id: str | None,
        client_request_id: str,
    ) -> dict[str, str | None]:
        request = {
            "from_agent_slug": str(from_agent_slug or "").strip(),
            "to_agent_slug": str(to_agent_slug or "").strip(),
            "message_text": common.normalize_text_input(str(message_text or "")).strip(),
            "thread_id": str(thread_id or "").strip() or None,
            "parent_thread_id": str(parent_thread_id or "").strip() or None,
            "client_request_id": client_request_id,
        }
        self._validate_message_request(request=request)
        return request

    def _validate_message_request(self, *, request: dict[str, str | None]) -> None:
        from_agent_slug = str(request["from_agent_slug"] or "")
        to_agent_slug = str(request["to_agent_slug"] or "")
        message_text = str(request["message_text"] or "")
        if not from_agent_slug or not to_agent_slug:
            raise common.ServiceError(400, "from_agent_slug and to_agent_slug are required")
        if from_agent_slug == to_agent_slug:
            raise common.ServiceError(400, "agent cannot send a thread message to itself")
        if not message_text:
            raise common.ServiceError(400, "message_text is required")

    async def _send_message_locked(self, *, request: dict[str, str | None]) -> JsonDict:
        message_request_context = self._message_request_context(request=request)
        async with self._lock:
            return await self._send_message_with_lock_context(message_request_context)

    async def _send_message_with_lock_context(self, message_request_context: JsonDict) -> JsonDict:
        cached = await self.store.get_idempotent_result(
            from_agent_slug=str(message_request_context["from_agent_slug"]),
            client_request_id=str(message_request_context["client_request_id"]),
        )
        if cached is not None:
            return cached
        response = await self._build_message_response(message_request_context)
        await self.store.save_idempotent_result(
            from_agent_slug=str(message_request_context["from_agent_slug"]),
            client_request_id=str(message_request_context["client_request_id"]),
            operation_name="message",
            response_payload=response,
        )
        return response

    async def _build_message_response(self, message_request_context: JsonDict) -> JsonDict:
        thread, created_thread = await self._resolve_message_thread(
            thread_id=self._optional_text(message_request_context.get("thread_id")),
            parent_thread_id=self._optional_text(message_request_context.get("parent_thread_id")),
            from_agent_slug=str(message_request_context["from_agent_slug"]),
            to_agent_slug=str(message_request_context["to_agent_slug"]),
        )
        event, thread_payload = await self.store.append_thread_event(
            request=AppendEventRequest(
                event_id=str(uuid.uuid4()),
                thread_id=str(thread.get("thread_id")),
                event_kind="message",
                notification_status=None,
                from_agent_slug=str(message_request_context["from_agent_slug"]),
                to_agent_slug=str(message_request_context["to_agent_slug"]),
                message_text=str(message_request_context["message_text"]),
                interrupts_runtime=True,
                requires_response=True,
                touch_activity=True,
                update_last_message_sender=True,
                set_thread_status="open",
            ),
        )
        return {
            "success": True,
            "operation": "message",
            "created_thread": created_thread,
            "thread": self.thread_summary(thread_payload),
            "event": event,
        }

    def _message_request_context(
        self,
        *,
        request: dict[str, str | None],
    ) -> JsonDict:
        return self._build_message_request_context(request)

    def _build_message_request_context(self, request: dict[str, str | None]) -> JsonDict:
        request_values = self._message_request_values(request)
        thread_context = self._message_thread_context(request_values)
        message_args = self._message_args(request_values)
        idempotency = self._message_idempotency(request_values)
        return {
            "thread_id": thread_context["thread_id"],
            "parent_thread_id": thread_context["parent_thread_id"],
            "from_agent_slug": message_args["from_agent_slug"],
            "to_agent_slug": message_args["to_agent_slug"],
            "message_text": message_args["message_text"],
            "client_request_id": idempotency["client_request_id"],
        }

    def _message_idempotency(self, request_values: dict[str, Any]) -> dict[str, str]:
        return {
            "from_agent_slug": str(request_values["from_agent_slug"]),
            "client_request_id": str(request_values["client_request_id"]),
        }

    def _message_args(self, request_values: dict[str, Any]) -> dict[str, str]:
        return {
            "from_agent_slug": str(request_values["from_agent_slug"]),
            "to_agent_slug": str(request_values["to_agent_slug"]),
            "message_text": str(request_values["message_text"]),
        }

    def _message_thread_context(self, request_values: dict[str, Any]) -> dict[str, str | None]:
        return {
            "thread_id": self._optional_text(request_values.get("thread_id")),
            "parent_thread_id": self._optional_text(request_values.get("parent_thread_id")),
        }

    def _optional_text(self, value: Any) -> str | None:
        normalized_value = str(value or "").strip()
        if normalized_value:
            return normalized_value
        return None

    def _message_request_values(self, request: dict[str, str | None]) -> JsonDict:
        return {
            "from_agent_slug": str(request["from_agent_slug"]),
            "to_agent_slug": str(request["to_agent_slug"]),
            "message_text": str(request["message_text"]),
            "thread_id": request["thread_id"],
            "parent_thread_id": request["parent_thread_id"],
            "client_request_id": str(request["client_request_id"]),
        }

    async def _resolve_message_thread(
        self,
        *,
        thread_id: str | None,
        parent_thread_id: str | None,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[dict[str, Any], bool]:
        if thread_id:
            return await self._resolve_existing_thread(
                thread_id=thread_id,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            )
        if parent_thread_id:
            return await self._resolve_child_thread(
                parent_thread_id=parent_thread_id,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            )
        return await self.store.get_or_create_root_thread(
            request=RootThreadRequest(
                thread_id=str(uuid.uuid4()),
                owner_agent_slug=from_agent_slug,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            ),
        )

    async def _resolve_existing_thread(
        self,
        *,
        thread_id: str,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[dict[str, Any], bool]:
        thread = await self.store.get_thread(thread_id)
        if thread is None:
            raise common.ServiceError(404, f"Unknown thread_id: {thread_id}")
        self.validate_routing(
            thread=thread,
            from_agent_slug=from_agent_slug,
            to_agent_slug=to_agent_slug,
        )
        return thread, False

    async def _resolve_child_thread(
        self,
        *,
        parent_thread_id: str,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[dict[str, Any], bool]:
        parent_thread = await self.store.get_thread(parent_thread_id)
        if parent_thread is None:
            raise common.ServiceError(404, f"Unknown parent_thread_id: {parent_thread_id}")
        parent_status = common.normalize_status(str(parent_thread.get("status") or ""))
        if parent_status in common.THREAD_TERMINAL_STATUSES:
            raise common.ServiceError(409, f"Parent thread {parent_thread_id} is already terminal")
        self.thread_peer_agent_slug(thread=parent_thread, agent_slug=from_agent_slug)
        return await self.store.get_or_create_child_thread(
            request=ChildThreadRequest(
                thread_id=str(uuid.uuid4()),
                root_thread_id=str(parent_thread.get("root_thread_id")),
                parent_thread_id=parent_thread_id,
                owner_agent_slug=from_agent_slug,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            ),
        )

    async def send_notification(  # noqa: WPS211
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        thread_id: str,
        status: str,
        message_text: str,
        client_request_id: str,
    ) -> dict[str, Any]:
        request = self._notification_request(
            from_agent_slug=from_agent_slug,
            to_agent_slug=to_agent_slug,
            thread_id=thread_id,
            status=status,
            message_text=message_text,
            client_request_id=client_request_id,
        )
        should_notify_stop = bool(request["status"] == "closed")
        should_cascade_close = bool(request["status"] in common.THREAD_TERMINAL_STATUSES)
        response = await self._send_notification_locked(request=request)
        if should_notify_stop:
            await self._notify_closed_thread(request=request)
        if should_cascade_close:
            await self._cascade_notification_close(request=request)
        return response

    def _notification_request(  # noqa: WPS211
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        thread_id: str,
        status: str,
        message_text: str,
        client_request_id: str,
    ) -> dict[str, str]:
        request = {
            "from_agent_slug": str(from_agent_slug or "").strip(),
            "to_agent_slug": str(to_agent_slug or "").strip(),
            "thread_id": str(thread_id or "").strip(),
            "status": common.normalize_status(status),
            "message_text": common.normalize_text_input(str(message_text or "")).strip(),
            "client_request_id": client_request_id,
        }
        self._validate_notification_request(request=request)
        return request

    def _validate_notification_request(self, *, request: dict[str, str]) -> None:
        if (
            not request["from_agent_slug"]
            or not request["to_agent_slug"]
            or not request["thread_id"]
        ):
            raise common.ServiceError(
                400, "from_agent_slug, to_agent_slug, and thread_id are required"
            )
        if request["status"] not in common.THREAD_NOTIFICATION_STATUSES:
            raise common.ServiceError(400, f"Unsupported notification status: {request['status']}")
        if not request["message_text"]:
            raise common.ServiceError(400, "message_text is required")

    async def _send_notification_locked(self, *, request: dict[str, str]) -> JsonDict:
        notification_context = self._notification_context(request=request)
        async with self._lock:
            return await self._send_notification_with_lock_context(notification_context)

    async def _send_notification_with_lock_context(
        self, notification_context: JsonDict
    ) -> JsonDict:
        cached = await self.store.get_idempotent_result(
            from_agent_slug=str(notification_context["from_agent_slug"]),
            client_request_id=str(notification_context["client_request_id"]),
        )
        if cached is not None:
            return cached
        thread = await self._notification_thread(notification_context)
        self._validate_notification_actor(thread=thread, notification_context=notification_context)
        response = await self._build_notification_response(notification_context)
        await self.store.save_idempotent_result(
            from_agent_slug=str(notification_context["from_agent_slug"]),
            client_request_id=str(notification_context["client_request_id"]),
            operation_name="notification",
            response_payload=response,
        )
        return response

    async def _notification_thread(self, notification_context: JsonDict) -> JsonDict:
        thread = await self.store.get_thread(str(notification_context["thread_id"]))
        if thread is None:
            raise common.ServiceError(
                404, f"Unknown thread_id: {notification_context['thread_id']}"
            )
        self.validate_routing(
            thread=thread,
            from_agent_slug=str(notification_context["from_agent_slug"]),
            to_agent_slug=str(notification_context["to_agent_slug"]),
        )
        return thread

    def _validate_notification_actor(
        self, *, thread: JsonDict, notification_context: JsonDict
    ) -> None:
        owner_agent_slug = str(thread.get("owner_agent_slug") or "").strip()
        allowed_statuses = self._allowed_notification_statuses(
            from_agent_slug=str(notification_context["from_agent_slug"]),
            owner_agent_slug=owner_agent_slug,
        )
        status = str(notification_context["status"])
        if status not in allowed_statuses:
            raise common.ServiceError(
                409,
                (
                    f"{notification_context['from_agent_slug']} cannot publish "
                    f"{status} on thread {notification_context['thread_id']}"
                ),
            )

    async def _build_notification_response(self, notification_context: JsonDict) -> JsonDict:
        status = str(notification_context["status"])
        thread_id = str(notification_context["thread_id"])
        event, thread_payload = await self.store.append_thread_event(
            request=AppendEventRequest(
                event_id=str(uuid.uuid4()),
                thread_id=thread_id,
                event_kind="notification",
                notification_status=status,
                from_agent_slug=str(notification_context["from_agent_slug"]),
                to_agent_slug=str(notification_context["to_agent_slug"]),
                message_text=str(notification_context["message_text"]),
                interrupts_runtime=bool(notification_context["requires_delivery"]),
                requires_response=False,
                touch_activity=bool(notification_context["requires_delivery"]),
                update_last_message_sender=False,
                set_thread_status=status,
                set_terminal=bool(notification_context["is_terminal"]),
            ),
        )
        if bool(notification_context["is_terminal"]):
            await self.store.cancel_pending_events_for_thread(
                thread_id=thread_id,
                reason=f"thread {thread_id} reached terminal state {status}",
            )
        return {
            "success": True,
            "operation": "notification",
            "thread": self.thread_summary(thread_payload),
            "event": event,
        }

    def _notification_context(
        self,
        *,
        request: dict[str, str],
    ) -> dict[str, Any]:
        request_values = self._notification_values(request)
        notification_core = self._notification_core(request_values)
        notification_delivery = self._notification_delivery(notification_core)
        idempotency = self._notification_idempotency(notification_core)
        return {
            "thread_id": notification_core["thread_id"],
            "from_agent_slug": notification_core["from_agent_slug"],
            "to_agent_slug": notification_core["to_agent_slug"],
            "status": notification_core["status"],
            "message_text": notification_core["message_text"],
            "requires_delivery": notification_delivery["requires_delivery"],
            "is_terminal": notification_delivery["is_terminal"],
            "client_request_id": idempotency["client_request_id"],
        }

    def _notification_delivery(self, notification_core: dict[str, str]) -> dict[str, bool]:
        status = notification_core["status"]
        return {
            "requires_delivery": status in common.DELIVERED_NOTIFICATION_STATUSES,
            "is_terminal": status in common.THREAD_TERMINAL_STATUSES,
        }

    def _notification_idempotency(self, notification_core: dict[str, str]) -> dict[str, str]:
        return {
            "from_agent_slug": notification_core["from_agent_slug"],
            "client_request_id": notification_core["client_request_id"],
        }

    def _notification_core(self, request_values: dict[str, str]) -> dict[str, str]:
        return {
            "from_agent_slug": request_values["from_agent_slug"],
            "to_agent_slug": request_values["to_agent_slug"],
            "thread_id": request_values["thread_id"],
            "status": request_values["status"],
            "message_text": request_values["message_text"],
            "client_request_id": request_values["client_request_id"],
        }

    def _notification_values(self, request: dict[str, str]) -> dict[str, str]:
        return {
            "from_agent_slug": request["from_agent_slug"],
            "to_agent_slug": request["to_agent_slug"],
            "thread_id": request["thread_id"],
            "status": request["status"],
            "message_text": request["message_text"],
            "client_request_id": request["client_request_id"],
        }

    def _allowed_notification_statuses(
        self,
        *,
        from_agent_slug: str,
        owner_agent_slug: str,
    ) -> frozenset[str]:
        if from_agent_slug == owner_agent_slug:
            return common.OWNER_NOTIFICATION_STATUSES
        return common.CALLEE_NOTIFICATION_STATUSES

    async def _notify_closed_thread(self, *, request: dict[str, str]) -> None:
        await self.notify_stop(
            agent_slug=request["to_agent_slug"],
            payload={
                "thread_id": request["thread_id"],
                "reason": (f"Thread {request['thread_id']} closed by {request['from_agent_slug']}"),
            },
        )

    async def _cascade_notification_close(self, *, request: dict[str, str]) -> None:
        await self.cascade_close_children(
            thread_id=request["thread_id"],
            reason=(
                f"parent thread {request['thread_id']} reached terminal state {request['status']}"
            ),
        )

    async def cascade_close_children(self, *, thread_id: str, reason: str) -> None:
        child_threads = await self.store.list_child_threads(parent_thread_id=thread_id)
        close_tasks = [
            self._close_child_thread(
                child_thread=child_thread, parent_thread_id=thread_id, reason=reason
            )
            for child_thread in child_threads
        ]
        await asyncio.gather(*close_tasks)

    async def _close_child_thread(
        self,
        *,
        child_thread: dict[str, Any],
        parent_thread_id: str,
        reason: str,
    ) -> None:
        child_thread_id = str(child_thread.get("thread_id") or "").strip()
        child_status = common.normalize_status(str(child_thread.get("status") or ""))
        if not child_thread_id or child_status in common.THREAD_TERMINAL_STATUSES:
            return
        participants = {
            str(child_thread.get("participant_a_agent_slug") or "").strip(),
            str(child_thread.get("participant_b_agent_slug") or "").strip(),
        }
        notify_tasks = [
            self.notify_stop(
                agent_slug=participant,
                payload={
                    "thread_id": child_thread_id,
                    "parent_thread_id": parent_thread_id,
                    "reason": reason,
                },
            )
            for participant in participants
            if participant
        ]
        await asyncio.gather(*notify_tasks)
        async with self._lock:
            await self.store.update_thread_terminal_status(
                thread_id=child_thread_id, status="closed"
            )
            await self.store.cancel_pending_events_for_thread(
                thread_id=child_thread_id,
                reason=f"thread {child_thread_id} closed because ancestor thread became terminal",
            )
        await self.cascade_close_children(
            thread_id=child_thread_id,
            reason=f"ancestor thread {parent_thread_id} closed descendant {child_thread_id}",
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
        return self._related_threads_payload(*self._related_threads_args(snapshot))

    def _related_threads_args(
        self,
        snapshot: JsonDict,
    ) -> tuple[list[JsonDict], JsonDict, str, str, str]:
        return self._related_threads_args_values(snapshot)

    def _related_threads_args_values(
        self,
        snapshot: JsonDict,
    ) -> tuple[list[JsonDict], JsonDict, str, str, str]:
        return self._unpack_related_threads_args(snapshot)

    def _unpack_related_threads_args(
        self,
        snapshot: JsonDict,
    ) -> tuple[list[JsonDict], JsonDict, str, str, str]:
        root_group, thread, thread_id = self._snapshot_parts(snapshot)
        relation_ids = self._relation_ids(thread)
        return (
            root_group,
            self._thread_payload(root_group=root_group, thread=thread, thread_id=thread_id),
            relation_ids[0],
            relation_ids[1],
            thread_id,
        )

    def _related_threads_payload(
        self,
        root_group: list[JsonDict],
        thread_payload: JsonDict,
        parent_thread_id: str,
        root_thread_id: str,
        thread_id: str,
    ) -> JsonDict:
        return {
            "thread": thread_payload,
            "parent_thread": self._thread_by_id(root_group=root_group, thread_id=parent_thread_id),
            "root_thread": self._thread_by_id(root_group=root_group, thread_id=root_thread_id),
            "child_threads": self._child_threads(root_group=root_group, thread_id=thread_id),
        }

    def _thread_payload(
        self,
        *,
        root_group: list[JsonDict],
        thread: JsonDict,
        thread_id: str,
    ) -> JsonDict:
        return next((item for item in root_group if item.get("thread_id") == thread_id), thread)

    def _relation_ids(self, thread: JsonDict) -> tuple[str, str]:
        parent_thread_id = str(thread.get("parent_thread_id") or "").strip()
        root_thread_id = str(thread.get("root_thread_id") or "").strip()
        return parent_thread_id, root_thread_id

    def _child_threads(self, *, root_group: list[JsonDict], thread_id: str) -> list[JsonDict]:
        return [item for item in root_group if item.get("parent_thread_id") == thread_id]

    def _snapshot_parts(
        self,
        snapshot: JsonDict,
    ) -> tuple[list[JsonDict], JsonDict, str]:
        root_group = list(snapshot["root_group"])
        thread = dict(snapshot["thread"])
        thread_id = str(snapshot["thread_id"])
        return root_group, thread, thread_id

    def _thread_by_id(
        self,
        *,
        root_group: list[JsonDict],
        thread_id: str,
    ) -> JsonDictOrNone:
        for item in root_group:
            if item.get("thread_id") == thread_id:
                return item
        return None

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
                await self._process_pending_events()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("delivery loop error: %s", exc, exc_info=True)
            await asyncio.sleep(self.delivery_poll_interval_seconds)

    async def _process_pending_events(self) -> None:
        async with self._lock:
            pending_events = await self.store.list_due_pending_events(
                now_iso=common.utc_now_iso(), limit=16
            )
        process_tasks = [self._process_pending_event_item(item=item) for item in pending_events]
        await asyncio.gather(*process_tasks)

    async def _process_pending_event_item(self, *, item: dict[str, Any]) -> None:
        event_id = str(item.get("event_id") or "").strip()
        target_agent_slug = str(item.get("to_agent_slug") or "").strip()
        if not event_id or not target_agent_slug:
            return
        callback_url = str(item.get("event_callback_url") or "").strip()
        if not callback_url:
            await self._mark_delivery_failed(
                event_id=event_id,
                error_text=(
                    f"target agent {target_agent_slug} is not registered or has no event callback"
                ),
            )
            return
        if not self.store.timestamp_within_lease(
            item.get("agent_last_seen_at"),
            lease_seconds=self.agent_lease_seconds,
        ):
            await self._mark_delivery_failed(
                event_id=event_id,
                error_text=f"target agent {target_agent_slug} is offline",
            )
            return
        await self._deliver_pending_event(item=item, callback_url=callback_url, event_id=event_id)

    async def _deliver_pending_event(
        self,
        *,
        item: dict[str, Any],
        callback_url: str,
        event_id: str,
    ) -> None:
        payload = {
            "delivery_id": str(uuid.uuid4()),
            "events": [
                {
                    "event_id": item.get("event_id"),
                    "thread_id": item.get("thread_id"),
                    "root_thread_id": item.get("root_thread_id"),
                    "parent_thread_id": item.get("parent_thread_id"),
                    "owner_agent_slug": item.get("owner_agent_slug"),
                    "sequence_no": item.get("sequence_no"),
                    "event_kind": item.get("event_kind"),
                    "notification_status": item.get("notification_status"),
                    "from_agent_slug": item.get("from_agent_slug"),
                    "to_agent_slug": item.get("to_agent_slug"),
                    "message_text": item.get("message_text"),
                    "interrupts_runtime": bool(item.get("interrupts_runtime")),
                    "requires_response": bool(item.get("requires_response")),
                    "created_at": item.get("created_at"),
                }
            ],
        }
        try:
            await self._post_delivery(callback_url=callback_url, payload=payload)
        except Exception as exc:
            logger.warning("event delivery failed for %s: %s", event_id, exc)
            await self._mark_delivery_failed(event_id=event_id, error_text=str(exc))
            return
        async with self._lock:
            await self.store.mark_event_delivered(event_id=event_id)

    async def _post_delivery(self, *, callback_url: str, payload: dict[str, Any]) -> None:
        assert self._http_session is not None
        async with self._http_session.post(callback_url, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"HTTP {response.status}: {body}")

    async def _mark_delivery_failed(self, *, event_id: str, error_text: str) -> None:
        async with self._lock:
            await self.store.mark_event_failed(
                event_id=event_id,
                error_text=error_text,
                retry_base_seconds=self.retry_base_seconds,
                retry_max_seconds=self.retry_max_seconds,
            )

    async def inactivity_loop(self) -> None:
        poll_interval = max(1.0, self.inactivity_timeout_seconds / 4.0)
        while self.running:
            try:
                await self._process_inactivity_candidates()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("inactivity loop error: %s", exc, exc_info=True)
            await asyncio.sleep(poll_interval)

    async def _process_inactivity_candidates(self) -> None:
        async with self._lock:
            candidates = await self.store.list_inactivity_candidates(
                timeout_seconds=self.inactivity_timeout_seconds,
                limit=32,
            )
        inactivity_tasks = [self._build_inactivity_task(thread=thread) for thread in candidates]
        await asyncio.gather(*inactivity_tasks)

    async def _build_inactivity_task(self, *, thread: dict[str, Any]) -> None:
        thread_id = str(thread.get("thread_id") or "").strip()
        recipient = str(thread.get("last_message_sender_agent_slug") or "").strip()
        last_activity_at = str(thread.get("last_activity_at") or "").strip()
        if not thread_id or not recipient:
            return
        message = (
            f"Thread {thread_id} has no new activity for at least "
            f"{self.inactivity_timeout_seconds} seconds since {last_activity_at}. "
            "You may resume it with a new message or close it."
        )
        await self._append_inactivity_event(
            thread_id=thread_id,
            recipient=recipient,
            message=message,
        )

    async def _append_inactivity_event(
        self,
        *,
        thread_id: str,
        recipient: str,
        message: str,
    ) -> None:
        async with self._lock:
            await self.store.append_thread_event(
                request=AppendEventRequest(
                    event_id=str(uuid.uuid4()),
                    thread_id=thread_id,
                    event_kind="inactive",
                    notification_status=None,
                    from_agent_slug="orchestra_threads",
                    to_agent_slug=recipient,
                    message_text=message,
                    interrupts_runtime=True,
                    requires_response=False,
                    touch_activity=False,
                    update_last_message_sender=False,
                ),
            )
            await self.store.mark_inactivity_sent(thread_id=thread_id)


def build_app(service: OrchestraThreadsService) -> web.Application:
    app = web.Application()
    handlers = http_handlers.HttpHandlers(service)
    app[SERVICE_APP_KEY] = service
    _register_routes(app=app, handlers=handlers)
    if service_shared.STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(service_shared.STATIC_DIR), show_index=False)
    return app


def _register_routes(*, app: web.Application, handlers: http_handlers.HttpHandlers) -> None:
    route_specs: tuple[tuple[str, str, Any], ...] = (
        ("get", "/", handlers.handle_ui),
        ("get", "/ui", handlers.handle_ui),
        ("get", "/healthz", handlers.handle_health),
        ("post", "/agents/register", handlers.handle_register),
        ("post", "/agents/heartbeat", handlers.handle_heartbeat),
        ("get", "/agents", handlers.handle_agents),
        ("get", "/api/v1/instructions", handlers.handle_instructions),
        ("post", "/api/v1/messages", handlers.handle_messages),
        ("post", "/api/v1/notifications", handlers.handle_notifications),
        ("get", "/api/v1/threads", handlers.handle_threads),
        ("get", "/api/v1/threads/{thread_id}/compact", handlers.handle_thread_compact),
        ("get", "/api/v1/threads/{thread_id}", handlers.handle_thread),
    )
    for method, path, handler in route_specs:
        getattr(app.router, f"add_{method}")(path, handler)
