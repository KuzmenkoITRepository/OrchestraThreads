"""HTTP service for OrchestraThreads backed by Postgres."""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

import aiohttp
from aiohttp import web

from .common import (
    CALLEE_NOTIFICATION_STATUSES,
    DELIVERED_NOTIFICATION_STATUSES,
    OWNER_NOTIFICATION_STATUSES,
    THREAD_NOTIFICATION_STATUSES,
    THREAD_TERMINAL_STATUSES,
    ServiceError,
    normalize_text_input,
    normalize_status,
    utc_now_iso,
)
from .guide import build_instruction_payload
from .store import ThreadStore


logger = logging.getLogger(__name__)
SERVICE_APP_KEY = web.AppKey("service", "OrchestraThreadsService")
STATIC_DIR = Path(__file__).with_name("static")


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


def _message_preview(text: str, *, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


class OrchestraThreadsService:
    """Thread service with retrying HTTP delivery and inactivity wakeups."""

    def __init__(
        self,
        *,
        database_url: Optional[str] = None,
        database_schema: Optional[str] = None,
        db_min_pool_size: Optional[int] = None,
        db_max_pool_size: Optional[int] = None,
        db_command_timeout_seconds: Optional[float] = None,
        db_path: Optional[str] = None,
        agent_lease_seconds: Optional[int] = None,
        delivery_poll_interval_seconds: Optional[float] = None,
        inactivity_timeout_seconds: Optional[int] = None,
        retry_base_seconds: Optional[int] = None,
        retry_max_seconds: Optional[int] = None,
    ) -> None:
        if db_path is not None:
            raise ValueError("SQLite support has been removed. Use database_url / ORCHESTRA_THREADS_DATABASE_URL.")
        self.database_url = str(
            database_url
            or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
            or "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads"
        ).strip()
        self.database_schema = str(
            database_schema
            or os.getenv("ORCHESTRA_THREADS_DB_SCHEMA")
            or "public"
        ).strip() or "public"
        self.db_min_pool_size = max(
            1,
            int(db_min_pool_size or os.getenv("ORCHESTRA_THREADS_DB_MIN_POOL_SIZE", "5")),
        )
        self.db_max_pool_size = max(
            self.db_min_pool_size,
            int(db_max_pool_size or os.getenv("ORCHESTRA_THREADS_DB_MAX_POOL_SIZE", "20")),
        )
        self.db_command_timeout_seconds = max(
            1.0,
            float(db_command_timeout_seconds or os.getenv("ORCHESTRA_THREADS_DB_COMMAND_TIMEOUT_SECONDS", "10")),
        )
        self.agent_lease_seconds = max(5, int(agent_lease_seconds or os.getenv("ORCHESTRA_THREADS_AGENT_LEASE_SECONDS", "30")))
        self.delivery_poll_interval_seconds = max(
            0.2,
            float(delivery_poll_interval_seconds or os.getenv("ORCHESTRA_THREADS_DELIVERY_POLL_INTERVAL_SECONDS", "1")),
        )
        self.inactivity_timeout_seconds = max(
            10,
            int(inactivity_timeout_seconds or os.getenv("ORCHESTRA_THREADS_INACTIVITY_TIMEOUT_SECONDS", "60")),
        )
        self.retry_base_seconds = max(1, int(retry_base_seconds or os.getenv("ORCHESTRA_THREADS_RETRY_BASE_SECONDS", "2")))
        self.retry_max_seconds = max(
            self.retry_base_seconds,
            int(retry_max_seconds or os.getenv("ORCHESTRA_THREADS_RETRY_MAX_SECONDS", "30")),
        )
        self.store = ThreadStore(
            self.database_url,
            schema_name=self.database_schema,
            min_pool_size=self.db_min_pool_size,
            max_pool_size=self.db_max_pool_size,
            command_timeout_seconds=self.db_command_timeout_seconds,
        )
        self._lock = asyncio.Lock()
        self._delivery_task: Optional[asyncio.Task[None]] = None
        self._inactivity_task: Optional[asyncio.Task[None]] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.running = False

    async def start(self) -> None:
        if self.running:
            return
        await self.store.start()
        try:
            self._http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
            self.running = True
            self._delivery_task = asyncio.create_task(self._delivery_loop(), name="orchestra-threads-delivery")
            self._inactivity_task = asyncio.create_task(self._inactivity_loop(), name="orchestra-threads-inactivity")
        except Exception:
            await self.store.close()
            raise

    async def stop(self) -> None:
        self.running = False
        for task in (self._delivery_task, self._inactivity_task):
            if task is not None:
                task.cancel()
        for task in (self._delivery_task, self._inactivity_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._delivery_task = None
        self._inactivity_task = None
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        await self.store.close()

    async def drop_storage(self) -> None:
        await self.store.drop_schema()

    def _thread_peer_agent_slug(self, *, thread: dict[str, Any], agent_slug: str) -> str:
        participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
        participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
        if participant_a == agent_slug:
            return participant_b
        if participant_b == agent_slug:
            return participant_a
        raise ServiceError(400, f"{agent_slug} is not a participant of thread {thread.get('thread_id')}")

    def _validate_routing(self, *, thread: dict[str, Any], from_agent_slug: str, to_agent_slug: str) -> None:
        if normalize_status(str(thread.get("status") or "")) in THREAD_TERMINAL_STATUSES:
            raise ServiceError(409, f"Thread {thread.get('thread_id')} is already terminal")
        expected_peer = self._thread_peer_agent_slug(thread=thread, agent_slug=from_agent_slug)
        if expected_peer != to_agent_slug:
            raise ServiceError(
                400,
                f"Thread {thread.get('thread_id')} expects peer {expected_peer}, got {to_agent_slug}",
            )

    def _thread_summary(self, thread: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if thread is None:
            return None
        payload = dict(thread)
        owner_agent_slug = str(payload.get("owner_agent_slug") or "").strip()
        participant_a_agent_slug = str(payload.get("participant_a_agent_slug") or "").strip()
        participant_b_agent_slug = str(payload.get("participant_b_agent_slug") or "").strip()
        peer_agent_slug = participant_a_agent_slug
        if owner_agent_slug == participant_a_agent_slug:
            peer_agent_slug = participant_b_agent_slug
        elif owner_agent_slug and owner_agent_slug == participant_b_agent_slug:
            peer_agent_slug = participant_a_agent_slug
        thread_scope = "root" if payload.get("thread_id") == payload.get("root_thread_id") else "child"
        agents = payload.get("agents")
        if not isinstance(agents, dict):
            agents = {
                "owner": self._agent_card_from_record(None, agent_slug=owner_agent_slug),
                "participant_a": self._agent_card_from_record(None, agent_slug=participant_a_agent_slug),
                "participant_b": self._agent_card_from_record(None, agent_slug=participant_b_agent_slug),
                "peer": self._agent_card_from_record(None, agent_slug=peer_agent_slug),
            }
        payload["is_terminal"] = normalize_status(str(payload.get("status") or "")) in THREAD_TERMINAL_STATUSES
        payload["scope"] = thread_scope
        payload["thread_scope"] = thread_scope
        payload["agents"] = agents
        payload["roles"] = payload.get("roles") or {
            "owner_agent_slug": owner_agent_slug,
            "peer_agent_slug": peer_agent_slug,
        }
        payload["pair_label"] = payload.get("pair_label") or (
            f"{payload['agents']['participant_a']['display_name']} "
            f"<-> {payload['agents']['participant_b']['display_name']}"
        )
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
                "message_preview": _message_preview(last_event_message_text),
            }
        return payload

    def _thread_compact_summary(
        self,
        *,
        thread: dict[str, Any],
        latest_event: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = self._thread_summary(thread) or {}
        latest = latest_event or {}
        payload["last_event_kind"] = latest.get("event_kind")
        payload["last_event_notification_status"] = latest.get("notification_status")
        payload["last_event_from_agent_slug"] = latest.get("from_agent_slug")
        payload["last_event_to_agent_slug"] = latest.get("to_agent_slug")
        payload["last_event_created_at"] = latest.get("created_at")
        payload["last_event_message_preview"] = _message_preview(str(latest.get("message_text") or ""))
        return payload

    def _agent_card_from_record(self, agent: Optional[dict[str, Any]], *, agent_slug: str) -> dict[str, Any]:
        normalized_slug = str(agent_slug or "").strip()
        payload = dict(agent or {})
        metadata = payload.get("metadata_json")
        metadata = metadata if isinstance(metadata, dict) else {}
        kind = str(metadata.get("kind") or "").strip()
        online = bool(
            agent
            and self.store.timestamp_within_lease(
                payload.get("last_seen_at"),
                lease_seconds=self.agent_lease_seconds,
            )
        )
        agent_type = str(metadata.get("agent_type") or "").strip()
        if not agent_type:
            agent_type = "manual_cli" if kind == "manual-cli-agent" else "registered"
        backend_type = str(metadata.get("backend_type") or "").strip() or kind or "unknown"
        display_name = str(payload.get("display_name") or normalized_slug).strip() or normalized_slug
        return {
            "slug": normalized_slug,
            "display_name": display_name,
            "agent_type": agent_type,
            "backend_type": backend_type,
            "active": online,
            "online": online,
            "metadata": metadata,
            "kind": kind or None,
        }

    def _event_payload(self, event: dict[str, Any], *, agents_by_slug: dict[str, dict[str, Any]]) -> dict[str, Any]:
        message_text = str(event.get("message_text") or "")
        from_agent_slug = str(event.get("from_agent_slug") or "").strip()
        to_agent_slug = str(event.get("to_agent_slug") or "").strip()
        return {
            "event_id": event.get("event_id"),
            "sequence_no": event.get("sequence_no"),
            "event_kind": event.get("event_kind"),
            "notification_status": event.get("notification_status"),
            "from_agent_slug": from_agent_slug,
            "to_agent_slug": to_agent_slug,
            "from_agent": self._agent_card_from_record(agents_by_slug.get(from_agent_slug), agent_slug=from_agent_slug),
            "to_agent": self._agent_card_from_record(agents_by_slug.get(to_agent_slug), agent_slug=to_agent_slug),
            "requires_action": bool(event.get("interrupts_runtime")) or bool(event.get("requires_response")),
            "interrupts_runtime": bool(event.get("interrupts_runtime")),
            "requires_response": bool(event.get("requires_response")),
            "pending_delivery": bool(event.get("pending_delivery")),
            "delivery_attempt_count": int(event.get("delivery_attempt_count") or 0),
            "last_delivery_error": event.get("last_delivery_error"),
            "created_at": event.get("created_at"),
            "message_text": message_text,
            "message_preview": _message_preview(message_text),
        }

    async def _agents_by_slug(self) -> dict[str, dict[str, Any]]:
        agents = await self.store.list_agents()
        return {
            str(agent.get("agent_slug") or "").strip(): agent
            for agent in agents
            if str(agent.get("agent_slug") or "").strip()
        }

    def _agent_view(self, agent: dict[str, Any]) -> dict[str, Any]:
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
            "time": utc_now_iso(),
        }
        return payload, 200 if self.running and db_ok else 503

    async def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_slug = str(payload.get("agent_slug") or "").strip()
        if not agent_slug:
            raise ServiceError(400, "agent_slug is required")
        base_url = str(payload.get("base_url") or "").strip()
        event_callback_url = str(payload.get("event_callback_url") or "").strip()
        stop_callback_url = str(payload.get("stop_callback_url") or "").strip()
        if base_url:
            normalized_base = base_url.rstrip("/")
            if not event_callback_url:
                event_callback_url = f"{normalized_base}/event"
            if not stop_callback_url:
                stop_callback_url = f"{normalized_base}/stop"
        if not event_callback_url or not stop_callback_url:
            raise ServiceError(400, "base_url or both callback URLs are required")
        async with self._lock:
            agent = await self.store.upsert_agent(
                agent_slug=agent_slug,
                display_name=str(payload.get("display_name") or agent_slug).strip() or agent_slug,
                event_callback_url=event_callback_url,
                stop_callback_url=stop_callback_url,
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
        return {
            "success": True,
            "agent": self._agent_view(agent),
            "agent_lease_seconds": self.agent_lease_seconds,
        }

    async def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_slug = str(payload.get("agent_slug") or "").strip()
        if not agent_slug:
            raise ServiceError(400, "agent_slug is required")
        async with self._lock:
            agent = await self.store.touch_agent(agent_slug=agent_slug)
        if agent is None:
            raise ServiceError(404, f"Unknown agent: {agent_slug}")
        return {
            "success": True,
            "agent": self._agent_view(agent),
        }

    async def list_agents(self) -> dict[str, Any]:
        async with self._lock:
            agents = [self._agent_view(agent) for agent in await self.store.list_agents()]
        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "agent_lease_seconds": self.agent_lease_seconds,
        }

    async def send_message(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        thread_id: Optional[str],
        parent_thread_id: Optional[str],
        client_request_id: str,
    ) -> dict[str, Any]:
        normalized_from = str(from_agent_slug or "").strip()
        normalized_to = str(to_agent_slug or "").strip()
        normalized_message = normalize_text_input(str(message_text or "")).strip()
        if not normalized_from or not normalized_to:
            raise ServiceError(400, "from_agent_slug and to_agent_slug are required")
        if normalized_from == normalized_to:
            raise ServiceError(400, "agent cannot send a thread message to itself")
        if not normalized_message:
            raise ServiceError(400, "message_text is required")

        async with self._lock:
            cached = await self.store.get_idempotent_result(
                from_agent_slug=normalized_from,
                client_request_id=client_request_id,
            )
            if cached is not None:
                return cached

            created_thread = False
            normalized_thread_id = str(thread_id or "").strip() or None
            normalized_parent_thread_id = str(parent_thread_id or "").strip() or None
            if normalized_thread_id:
                thread = await self.store.get_thread(normalized_thread_id)
                if thread is None:
                    raise ServiceError(404, f"Unknown thread_id: {normalized_thread_id}")
                self._validate_routing(
                    thread=thread,
                    from_agent_slug=normalized_from,
                    to_agent_slug=normalized_to,
                )
            elif normalized_parent_thread_id:
                parent_thread = await self.store.get_thread(normalized_parent_thread_id)
                if parent_thread is None:
                    raise ServiceError(404, f"Unknown parent_thread_id: {normalized_parent_thread_id}")
                if normalize_status(str(parent_thread.get("status") or "")) in THREAD_TERMINAL_STATUSES:
                    raise ServiceError(409, f"Parent thread {normalized_parent_thread_id} is already terminal")
                self._thread_peer_agent_slug(thread=parent_thread, agent_slug=normalized_from)
                thread, created_thread = await self.store.get_or_create_child_thread(
                    thread_id=str(uuid.uuid4()),
                    root_thread_id=str(parent_thread.get("root_thread_id")),
                    parent_thread_id=normalized_parent_thread_id,
                    owner_agent_slug=normalized_from,
                    from_agent_slug=normalized_from,
                    to_agent_slug=normalized_to,
                )
            else:
                thread, created_thread = await self.store.get_or_create_root_thread(
                    thread_id=str(uuid.uuid4()),
                    owner_agent_slug=normalized_from,
                    from_agent_slug=normalized_from,
                    to_agent_slug=normalized_to,
                )

            event, thread_payload = await self.store.append_thread_event(
                event_id=str(uuid.uuid4()),
                thread_id=str(thread.get("thread_id")),
                event_kind="message",
                notification_status=None,
                from_agent_slug=normalized_from,
                to_agent_slug=normalized_to,
                message_text=normalized_message,
                interrupts_runtime=True,
                requires_response=True,
                touch_activity=True,
                update_last_message_sender=True,
                set_thread_status="open",
            )
            response = {
                "success": True,
                "operation": "message",
                "created_thread": created_thread,
                "thread": self._thread_summary(thread_payload),
                "event": event,
            }
            await self.store.save_idempotent_result(
                from_agent_slug=normalized_from,
                client_request_id=client_request_id,
                operation_name="message",
                response_payload=response,
            )
            return response

    async def send_notification(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        thread_id: str,
        status: str,
        message_text: str,
        client_request_id: str,
    ) -> dict[str, Any]:
        normalized_from = str(from_agent_slug or "").strip()
        normalized_to = str(to_agent_slug or "").strip()
        normalized_thread_id = str(thread_id or "").strip()
        normalized_status = normalize_status(status)
        normalized_message = normalize_text_input(str(message_text or "")).strip()
        if not normalized_from or not normalized_to or not normalized_thread_id:
            raise ServiceError(400, "from_agent_slug, to_agent_slug, and thread_id are required")
        if normalized_status not in THREAD_NOTIFICATION_STATUSES:
            raise ServiceError(400, f"Unsupported notification status: {normalized_status}")
        if not normalized_message:
            raise ServiceError(400, "message_text is required")

        should_notify_stop = False
        should_cascade_close = False
        async with self._lock:
            cached = await self.store.get_idempotent_result(
                from_agent_slug=normalized_from,
                client_request_id=client_request_id,
            )
            if cached is not None:
                return cached

            thread = await self.store.get_thread(normalized_thread_id)
            if thread is None:
                raise ServiceError(404, f"Unknown thread_id: {normalized_thread_id}")
            self._validate_routing(thread=thread, from_agent_slug=normalized_from, to_agent_slug=normalized_to)

            owner_agent_slug = str(thread.get("owner_agent_slug") or "").strip()
            allowed_statuses = OWNER_NOTIFICATION_STATUSES if normalized_from == owner_agent_slug else CALLEE_NOTIFICATION_STATUSES
            if normalized_status not in allowed_statuses:
                raise ServiceError(409, f"{normalized_from} cannot publish {normalized_status} on thread {normalized_thread_id}")

            requires_delivery = normalized_status in DELIVERED_NOTIFICATION_STATUSES
            event, thread_payload = await self.store.append_thread_event(
                event_id=str(uuid.uuid4()),
                thread_id=normalized_thread_id,
                event_kind="notification",
                notification_status=normalized_status,
                from_agent_slug=normalized_from,
                to_agent_slug=normalized_to,
                message_text=normalized_message,
                interrupts_runtime=requires_delivery,
                requires_response=False,
                touch_activity=requires_delivery,
                update_last_message_sender=False,
                set_thread_status=normalized_status,
                set_terminal=normalized_status in THREAD_TERMINAL_STATUSES,
            )
            should_notify_stop = normalized_status == "closed"
            should_cascade_close = normalized_status in THREAD_TERMINAL_STATUSES
            if normalized_status in THREAD_TERMINAL_STATUSES:
                await self.store.cancel_pending_events_for_thread(
                    thread_id=normalized_thread_id,
                    reason=f"thread {normalized_thread_id} reached terminal state {normalized_status}",
                )

            response = {
                "success": True,
                "operation": "notification",
                "thread": self._thread_summary(thread_payload),
                "event": event,
            }
            await self.store.save_idempotent_result(
                from_agent_slug=normalized_from,
                client_request_id=client_request_id,
                operation_name="notification",
                response_payload=response,
            )
        if should_notify_stop:
            await self._notify_stop(
                agent_slug=normalized_to,
                payload={
                    "thread_id": normalized_thread_id,
                    "reason": f"Thread {normalized_thread_id} closed by {normalized_from}",
                },
            )
        if should_cascade_close:
            await self._cascade_close_children(
                thread_id=normalized_thread_id,
                reason=f"parent thread {normalized_thread_id} reached terminal state {normalized_status}",
            )
        return response

    async def _cascade_close_children(self, *, thread_id: str, reason: str) -> None:
        child_threads = await self.store.list_child_threads(parent_thread_id=thread_id)
        for child_thread in child_threads:
            child_thread_id = str(child_thread.get("thread_id") or "").strip()
            child_status = normalize_status(str(child_thread.get("status") or ""))
            if not child_thread_id or child_status in THREAD_TERMINAL_STATUSES:
                continue
            participants = {
                str(child_thread.get("participant_a_agent_slug") or "").strip(),
                str(child_thread.get("participant_b_agent_slug") or "").strip(),
            }
            for participant in participants:
                if participant:
                    await self._notify_stop(
                        agent_slug=participant,
                        payload={
                            "thread_id": child_thread_id,
                            "parent_thread_id": thread_id,
                            "reason": reason,
                        },
                    )
            async with self._lock:
                await self.store.update_thread_terminal_status(thread_id=child_thread_id, status="closed")
                await self.store.cancel_pending_events_for_thread(
                    thread_id=child_thread_id,
                    reason=f"thread {child_thread_id} closed because ancestor thread became terminal",
                )
            await self._cascade_close_children(
                thread_id=child_thread_id,
                reason=f"ancestor thread {thread_id} closed descendant {child_thread_id}",
            )

    async def list_threads(self, *, scope: str, limit: int) -> dict[str, Any]:
        normalized_scope = str(scope or "active").strip().lower()
        if normalized_scope not in {"active", "all"}:
            raise ServiceError(400, "scope must be active or all")
        async with self._lock:
            agents_by_slug = await self._agents_by_slug()
            threads = [
                self._thread_summary(
                    self._inject_agent_cards(thread=thread, agents_by_slug=agents_by_slug)
                )
                for thread in await self.store.list_threads(active_only=normalized_scope == "active", limit=max(1, limit))
            ]
        return {
            "success": True,
            "scope": normalized_scope,
            "threads": threads,
        }

    async def get_thread(self, *, thread_id: str, limit: int) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            raise ServiceError(400, "thread_id is required")
        async with self._lock:
            agents_by_slug = await self._agents_by_slug()
            thread = await self.store.get_thread(normalized_thread_id)
            if thread is None:
                raise ServiceError(404, f"Unknown thread_id: {normalized_thread_id}")
            raw_events = await self.store.list_thread_events(thread_id=normalized_thread_id, limit=max(1, limit))
            root_group = await self.store.list_threads_by_root(root_thread_id=str(thread.get("root_thread_id")))
        events = [self._event_payload(event, agents_by_slug=agents_by_slug) for event in raw_events]
        thread_payload = next((item for item in root_group if item.get("thread_id") == normalized_thread_id), thread)
        parent_thread_id = str(thread.get("parent_thread_id") or "").strip()
        root_thread_id = str(thread.get("root_thread_id") or "").strip()
        parent_thread = next((item for item in root_group if item.get("thread_id") == parent_thread_id), None)
        root_thread = next((item for item in root_group if item.get("thread_id") == root_thread_id), None)
        child_threads = [item for item in root_group if item.get("parent_thread_id") == normalized_thread_id]
        return {
            "success": True,
            "thread": self._thread_summary(self._inject_agent_cards(thread=thread_payload, agents_by_slug=agents_by_slug)),
            "events": events,
            "related": {
                "parent_thread": self._thread_summary(
                    self._inject_agent_cards(thread=parent_thread, agents_by_slug=agents_by_slug)
                ),
                "root_thread": self._thread_summary(
                    self._inject_agent_cards(thread=root_thread, agents_by_slug=agents_by_slug)
                ),
                "child_threads": [
                    self._thread_summary(self._inject_agent_cards(thread=item, agents_by_slug=agents_by_slug))
                    for item in child_threads
                ],
                "root_group": [
                    self._thread_summary(self._inject_agent_cards(thread=item, agents_by_slug=agents_by_slug))
                    for item in root_group
                ],
            },
        }

    def _inject_agent_cards(
        self,
        *,
        thread: Optional[dict[str, Any]],
        agents_by_slug: dict[str, dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if thread is None:
            return None
        payload = dict(thread)
        owner_agent_slug = str(payload.get("owner_agent_slug") or "").strip()
        participant_a_agent_slug = str(payload.get("participant_a_agent_slug") or "").strip()
        participant_b_agent_slug = str(payload.get("participant_b_agent_slug") or "").strip()
        peer_agent_slug = participant_a_agent_slug
        if owner_agent_slug == participant_a_agent_slug:
            peer_agent_slug = participant_b_agent_slug
        elif owner_agent_slug and owner_agent_slug == participant_b_agent_slug:
            peer_agent_slug = participant_a_agent_slug
        payload["agents"] = {
            "owner": self._agent_card_from_record(agents_by_slug.get(owner_agent_slug), agent_slug=owner_agent_slug),
            "participant_a": self._agent_card_from_record(
                agents_by_slug.get(participant_a_agent_slug),
                agent_slug=participant_a_agent_slug,
            ),
            "participant_b": self._agent_card_from_record(
                agents_by_slug.get(participant_b_agent_slug),
                agent_slug=participant_b_agent_slug,
            ),
            "peer": self._agent_card_from_record(agents_by_slug.get(peer_agent_slug), agent_slug=peer_agent_slug),
        }
        payload["roles"] = {
            "owner_agent_slug": owner_agent_slug,
            "peer_agent_slug": peer_agent_slug,
        }
        payload["pair_label"] = (
            f"{payload['agents']['participant_a']['display_name']} "
            f"<-> {payload['agents']['participant_b']['display_name']}"
        )
        return payload

    async def get_thread_compact(self, *, thread_id: str) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            raise ServiceError(400, "thread_id is required")
        async with self._lock:
            thread = await self.store.get_thread(normalized_thread_id)
            if thread is None:
                raise ServiceError(404, f"Unknown thread_id: {normalized_thread_id}")
            latest_event = await self.store.get_latest_thread_event(thread_id=normalized_thread_id)
        return {
            "success": True,
            "thread": self._thread_compact_summary(thread=thread, latest_event=latest_event),
        }

    async def get_instruction(self, *, view: str, section: Optional[str]) -> dict[str, Any]:
        try:
            instruction = build_instruction_payload(view=view, section=section)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc
        return {
            "success": True,
            "instruction": instruction,
        }

    async def _notify_stop(self, *, agent_slug: str, payload: dict[str, Any]) -> None:
        session = self._http_session
        if session is None:
            return
        async with self._lock:
            agent = await self.store.get_agent(agent_slug)
        if agent is None:
            return
        if not self.store.timestamp_within_lease(agent.get("last_seen_at"), lease_seconds=self.agent_lease_seconds):
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

    async def _delivery_loop(self) -> None:
        while self.running:
            try:
                async with self._lock:
                    pending_events = await self.store.list_due_pending_events(now_iso=utc_now_iso(), limit=16)
                for item in pending_events:
                    event_id = str(item.get("event_id") or "").strip()
                    target_agent_slug = str(item.get("to_agent_slug") or "").strip()
                    if not event_id or not target_agent_slug:
                        continue
                    callback_url = str(item.get("event_callback_url") or "").strip()
                    if not callback_url:
                        async with self._lock:
                            await self.store.mark_event_failed(
                                event_id=event_id,
                                error_text=f"target agent {target_agent_slug} is not registered or has no event callback",
                                retry_base_seconds=self.retry_base_seconds,
                                retry_max_seconds=self.retry_max_seconds,
                            )
                        continue
                    if not self.store.timestamp_within_lease(
                        item.get("agent_last_seen_at"),
                        lease_seconds=self.agent_lease_seconds,
                    ):
                        async with self._lock:
                            await self.store.mark_event_failed(
                                event_id=event_id,
                                error_text=f"target agent {target_agent_slug} is offline",
                                retry_base_seconds=self.retry_base_seconds,
                                retry_max_seconds=self.retry_max_seconds,
                            )
                        continue
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
                        assert self._http_session is not None
                        async with self._http_session.post(callback_url, json=payload) as response:
                            if response.status >= 400:
                                body = await response.text()
                                raise RuntimeError(f"HTTP {response.status}: {body}")
                        async with self._lock:
                            await self.store.mark_event_delivered(event_id=event_id)
                    except Exception as exc:
                        logger.warning("event delivery failed for %s: %s", event_id, exc)
                        async with self._lock:
                            await self.store.mark_event_failed(
                                event_id=event_id,
                                error_text=str(exc),
                                retry_base_seconds=self.retry_base_seconds,
                                retry_max_seconds=self.retry_max_seconds,
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("delivery loop error: %s", exc, exc_info=True)
            await asyncio.sleep(self.delivery_poll_interval_seconds)

    async def _inactivity_loop(self) -> None:
        poll_interval = max(1.0, self.inactivity_timeout_seconds / 4.0)
        while self.running:
            try:
                async with self._lock:
                    candidates = await self.store.list_inactivity_candidates(
                        timeout_seconds=self.inactivity_timeout_seconds,
                        limit=32,
                    )
                for thread in candidates:
                    thread_id = str(thread.get("thread_id") or "").strip()
                    recipient = str(thread.get("last_message_sender_agent_slug") or "").strip()
                    last_activity_at = str(thread.get("last_activity_at") or "").strip()
                    if not thread_id or not recipient:
                        continue
                    message = (
                        f"Thread {thread_id} has no new activity for at least "
                        f"{self.inactivity_timeout_seconds} seconds since {last_activity_at}. "
                        "You may resume it with a new message or close it."
                    )
                    async with self._lock:
                        await self.store.append_thread_event(
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
                        )
                        await self.store.mark_inactivity_sent(thread_id=thread_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("inactivity loop error: %s", exc, exc_info=True)
            await asyncio.sleep(poll_interval)


def build_app(service: OrchestraThreadsService) -> web.Application:
    app = web.Application()
    app[SERVICE_APP_KEY] = service

    async def handle_ui(_: web.Request) -> web.Response:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return _json_error("OrchestraThreads UI is not available", status=404)
        return web.FileResponse(index_path)

    async def handle_health(_: web.Request) -> web.Response:
        payload, status_code = await service.health_snapshot()
        return web.json_response(payload, status=status_code)

    async def handle_register(request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            result = await service.register_agent(payload)
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_heartbeat(request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            result = await service.heartbeat(payload)
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_agents(_: web.Request) -> web.Response:
        try:
            result = await service.list_agents()
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_messages(request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            result = await service.send_message(
                from_agent_slug=str(payload.get("from_agent_slug") or "").strip(),
                to_agent_slug=str(payload.get("to_agent_slug") or "").strip(),
                message_text=str(payload.get("message_text") or ""),
                thread_id=str(payload.get("thread_id") or "").strip() or None,
                parent_thread_id=str(payload.get("parent_thread_id") or "").strip() or None,
                client_request_id=str(payload.get("client_request_id") or "").strip() or uuid.uuid4().hex,
            )
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)
        except Exception as exc:
            logger.error("message request failed: %s\n%s", exc, traceback.format_exc())
            return _json_error(str(exc) or "internal server error", status=500)

    async def handle_notifications(request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            result = await service.send_notification(
                from_agent_slug=str(payload.get("from_agent_slug") or "").strip(),
                to_agent_slug=str(payload.get("to_agent_slug") or "").strip(),
                thread_id=str(payload.get("thread_id") or "").strip(),
                status=str(payload.get("status") or "").strip(),
                message_text=str(payload.get("message_text") or ""),
                client_request_id=str(payload.get("client_request_id") or "").strip() or uuid.uuid4().hex,
            )
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)
        except Exception as exc:
            logger.error("notification request failed: %s\n%s", exc, traceback.format_exc())
            return _json_error(str(exc) or "internal server error", status=500)

    async def handle_threads(request: web.Request) -> web.Response:
        try:
            result = await service.list_threads(
                scope=str(request.query.get("scope", "active")),
                limit=max(1, int(request.query.get("limit", "100"))),
            )
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_thread(request: web.Request) -> web.Response:
        try:
            result = await service.get_thread(
                thread_id=str(request.match_info.get("thread_id") or ""),
                limit=max(1, int(request.query.get("limit", "200"))),
            )
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_thread_compact(request: web.Request) -> web.Response:
        try:
            result = await service.get_thread_compact(
                thread_id=str(request.match_info.get("thread_id") or ""),
            )
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_instructions(request: web.Request) -> web.Response:
        try:
            result = await service.get_instruction(
                view=str(request.query.get("view", "compact")),
                section=str(request.query.get("section") or "").strip() or None,
            )
            return web.json_response(result)
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    app.router.add_get("/", handle_ui)
    app.router.add_get("/ui", handle_ui)
    if STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(STATIC_DIR), show_index=False)
    app.router.add_get("/healthz", handle_health)
    app.router.add_post("/agents/register", handle_register)
    app.router.add_post("/agents/heartbeat", handle_heartbeat)
    app.router.add_get("/agents", handle_agents)
    app.router.add_get("/api/v1/instructions", handle_instructions)
    app.router.add_post("/api/v1/messages", handle_messages)
    app.router.add_post("/api/v1/notifications", handle_notifications)
    app.router.add_get("/api/v1/threads", handle_threads)
    app.router.add_get("/api/v1/threads/{thread_id}/compact", handle_thread_compact)
    app.router.add_get("/api/v1/threads/{thread_id}", handle_thread)
    return app
