"""Compact async client used by the local MCP server and future runtimes."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import aiohttp


class OrchestraThreadsClient:
    """Async HTTP client for the OrchestraThreads service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = str(
            base_url or os.getenv("ORCHESTRA_THREADS_URL") or "http://127.0.0.1:8788"
        ).rstrip("/")
        self.timeout_seconds = max(
            1.0,
            float(timeout_seconds or os.getenv("ORCHESTRA_THREADS_HTTP_TIMEOUT_SECONDS", "10")),
        )
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _session_or_create(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            )
        return self._session

    async def _request(
        self,
        *,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._session_or_create()
        async with session.request(
            method,
            f"{self.base_url}{path}",
            json=json_payload,
        ) as response:
            raw = await response.text()
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                if response.status >= 400:
                    raise RuntimeError(raw.strip() or f"HTTP {response.status}") from None
                raise RuntimeError(
                    f"OrchestraThreads returned a non-JSON response with HTTP {response.status}"
                ) from None
            if response.status >= 400:
                raise RuntimeError(str(payload.get("error") or payload))
            if isinstance(payload, dict):
                return payload
            raise RuntimeError("OrchestraThreads returned a non-object response")

    async def send_message(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        thread_id: str | None = None,
        parent_thread_id: str | None = None,
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            method="POST",
            path="/api/v1/messages",
            json_payload={
                "from_agent_slug": from_agent_slug,
                "to_agent_slug": to_agent_slug,
                "message_text": message_text,
                "thread_id": thread_id,
                "parent_thread_id": parent_thread_id,
                "client_request_id": client_request_id or uuid.uuid4().hex,
            },
        )

    async def register_agent(
        self,
        *,
        agent_slug: str,
        base_url: str | None = None,
        display_name: str | None = None,
        event_callback_url: str | None = None,
        stop_callback_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            method="POST",
            path="/agents/register",
            json_payload={
                "agent_slug": agent_slug,
                "display_name": display_name,
                "base_url": base_url,
                "event_callback_url": event_callback_url,
                "stop_callback_url": stop_callback_url,
                "metadata": metadata or {},
            },
        )

    async def heartbeat(self, *, agent_slug: str) -> dict[str, Any]:
        return await self._request(
            method="POST",
            path="/agents/heartbeat",
            json_payload={
                "agent_slug": agent_slug,
            },
        )

    async def list_agents(self) -> dict[str, Any]:
        return await self._request(
            method="GET",
            path="/agents",
        )

    async def send_notification(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        thread_id: str,
        status: str,
        message_text: str,
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            method="POST",
            path="/api/v1/notifications",
            json_payload={
                "from_agent_slug": from_agent_slug,
                "to_agent_slug": to_agent_slug,
                "thread_id": thread_id,
                "status": status,
                "message_text": message_text,
                "client_request_id": client_request_id or uuid.uuid4().hex,
            },
        )

    async def get_thread(self, *, thread_id: str, limit: int | None = None) -> dict[str, Any]:
        suffix = ""
        if limit is not None:
            suffix = f"?limit={max(1, int(limit))}"
        return await self._request(
            method="GET",
            path=f"/api/v1/threads/{thread_id}{suffix}",
        )

    async def get_thread_compact(self, *, thread_id: str) -> dict[str, Any]:
        return await self._request(
            method="GET",
            path=f"/api/v1/threads/{thread_id}/compact",
        )

    async def get_instruction(
        self, *, view: str = "compact", section: str | None = None
    ) -> dict[str, Any]:
        suffix = f"?view={str(view or 'compact').strip() or 'compact'}"
        if section:
            suffix += f"&section={str(section).strip()}"
        return await self._request(
            method="GET",
            path=f"/api/v1/instructions{suffix}",
        )

    async def list_threads(self, *, scope: str = "active", limit: int = 100) -> dict[str, Any]:
        return await self._request(
            method="GET",
            path=f"/api/v1/threads?scope={scope}&limit={max(1, int(limit))}",
        )
