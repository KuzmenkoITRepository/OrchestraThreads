"""Compact async client used by the local MCP server and future runtimes."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True, slots=True)
class SendMessageRequest:
    from_agent_slug: str
    to_agent_slug: str
    message_text: str
    thread_id: str | None
    parent_thread_id: str | None
    client_request_id: str | None


@dataclass(frozen=True, slots=True)
class RegisterAgentRequest:
    agent_slug: str
    base_url: str | None
    display_name: str | None
    event_callback_url: str | None
    stop_callback_url: str | None
    metadata: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class SendNotificationRequest:
    from_agent_slug: str
    to_agent_slug: str
    thread_id: str
    status: str
    message_text: str
    client_request_id: str | None


class _ThreadsTransport:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def request(
        self,
        *,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._session_or_create()
        async with session.request(
            method,
            self._build_url(path),
            json=json_payload,
        ) as response:
            payload = self._parse_payload(await response.text(), status=response.status)
            if response.status >= 400:
                raise RuntimeError(str(payload.get("error") or payload))
            if isinstance(payload, dict):
                return payload
            raise RuntimeError("OrchestraThreads returned a non-object response")

    async def _session_or_create(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            )
        return self._session

    def _build_url(self, path: str) -> str:
        return "".join((self.base_url, path))

    def _parse_payload(self, raw_body: str, *, status: int) -> Any:
        try:
            return json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            if status >= 400:
                raise RuntimeError(raw_body.strip() or f"HTTP {status}") from None
            raise RuntimeError(
                f"OrchestraThreads returned a non-JSON response with HTTP {status}"
            ) from None


class _ThreadsApi:  # noqa: WPS214  # HTTP API client needs one method per service endpoint.
    def __init__(self, *, transport: _ThreadsTransport) -> None:
        self._transport = transport

    async def heartbeat(self, *, agent_slug: str) -> dict[str, Any]:
        return await self._transport.request(
            method="POST",
            path="/agents/heartbeat",
            json_payload={"agent_slug": agent_slug},
        )

    async def list_agents(self) -> dict[str, Any]:
        return await self._transport.request(method="GET", path="/agents")

    async def get_agent_status(self, *, agent_slug: str) -> dict[str, Any]:
        normalized_slug = str(agent_slug).strip()
        if not normalized_slug:
            raise RuntimeError("agent_slug is required")
        return await self._transport.request(
            method="GET",
            path=f"/agents/{normalized_slug}/status",
        )

    async def get_thread(self, *, thread_id: str, limit: int | None = None) -> dict[str, Any]:
        suffix = ""
        if limit is not None:
            suffix = f"?limit={max(1, int(limit))}"
        return await self._transport.request(
            method="GET",
            path=f"/api/v1/threads/{thread_id}{suffix}",
        )

    async def get_thread_compact(self, *, thread_id: str) -> dict[str, Any]:
        return await self._transport.request(
            method="GET",
            path=f"/api/v1/threads/{thread_id}/compact",
        )

    async def get_instruction(
        self,
        *,
        view: str = "compact",
        section: str | None = None,
    ) -> dict[str, Any]:
        query = f"view={str(view or 'compact').strip() or 'compact'}"
        if section:
            query = f"{query}&section={str(section).strip()}"
        return await self._transport.request(
            method="GET",
            path=f"/api/v1/instructions?{query}",
        )

    async def list_threads(self, *, scope: str = "active", limit: int = 100) -> dict[str, Any]:
        return await self._transport.request(
            method="GET",
            path=f"/api/v1/threads?scope={scope}&limit={max(1, int(limit))}",
        )


class OrchestraThreadsClient:
    """Async HTTP client for the OrchestraThreads service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        resolved_base_url = str(
            base_url or os.getenv("ORCHESTRA_THREADS_URL") or "http://127.0.0.1:8788"
        ).rstrip("/")
        raw_timeout: float | str
        if timeout_seconds is None:
            raw_timeout = os.getenv("ORCHESTRA_THREADS_HTTP_TIMEOUT_SECONDS", "10")
        else:
            raw_timeout = timeout_seconds
        self._transport = _ThreadsTransport(
            base_url=resolved_base_url,
            timeout_seconds=max(1.0, float(raw_timeout)),
        )
        self._api = _ThreadsApi(transport=self._transport)
        self.base_url = resolved_base_url
        self.timeout_seconds = self._transport.timeout_seconds

    async def close(self) -> None:
        await self._transport.close()

    async def send_message(self, **kwargs: Any) -> dict[str, Any]:
        request = SendMessageRequest(
            from_agent_slug=kwargs["from_agent_slug"],
            to_agent_slug=kwargs["to_agent_slug"],
            message_text=kwargs["message_text"],
            thread_id=kwargs.get("thread_id"),
            parent_thread_id=kwargs.get("parent_thread_id"),
            client_request_id=kwargs.get("client_request_id"),
        )
        return await self._transport.request(
            method="POST",
            path="/api/v1/messages",
            json_payload={
                "from_agent_slug": request.from_agent_slug,
                "to_agent_slug": request.to_agent_slug,
                "message_text": request.message_text,
                "thread_id": request.thread_id,
                "parent_thread_id": request.parent_thread_id,
                "client_request_id": request.client_request_id or uuid.uuid4().hex,
            },
        )

    async def register_agent(self, **kwargs: Any) -> dict[str, Any]:
        request = RegisterAgentRequest(
            agent_slug=kwargs["agent_slug"],
            base_url=kwargs.get("base_url"),
            display_name=kwargs.get("display_name"),
            event_callback_url=kwargs.get("event_callback_url"),
            stop_callback_url=kwargs.get("stop_callback_url"),
            metadata=kwargs.get("metadata"),
        )
        return await self._transport.request(
            method="POST",
            path="/agents/register",
            json_payload={
                "agent_slug": request.agent_slug,
                "display_name": request.display_name,
                "base_url": request.base_url,
                "event_callback_url": request.event_callback_url,
                "stop_callback_url": request.stop_callback_url,
                "metadata": request.metadata or {},
            },
        )

    async def send_notification(self, **kwargs: Any) -> dict[str, Any]:
        request = SendNotificationRequest(
            from_agent_slug=kwargs["from_agent_slug"],
            to_agent_slug=kwargs["to_agent_slug"],
            thread_id=kwargs["thread_id"],
            status=kwargs["status"],
            message_text=kwargs["message_text"],
            client_request_id=kwargs.get("client_request_id"),
        )
        return await self._transport.request(
            method="POST",
            path="/api/v1/notifications",
            json_payload={
                "from_agent_slug": request.from_agent_slug,
                "to_agent_slug": request.to_agent_slug,
                "thread_id": request.thread_id,
                "status": request.status,
                "message_text": request.message_text,
                "client_request_id": request.client_request_id or uuid.uuid4().hex,
            },
        )

    def __getattr__(self, name: str) -> Any:
        if name in {
            "heartbeat",
            "list_agents",
            "get_agent_status",
            "get_thread",
            "get_thread_compact",
            "get_instruction",
            "list_threads",
        }:
            return getattr(self._api, name)
        raise AttributeError(name)
