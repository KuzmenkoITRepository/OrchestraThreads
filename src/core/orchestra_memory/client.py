from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True, slots=True)
class _MemoryClientConfig:
    base_url: str
    timeout_seconds: float


class _MemoryTransport:
    def __init__(
        self,
        *,
        config: _MemoryClientConfig,
    ) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def request(self, *, path: str, json_payload: dict[str, Any]) -> dict[str, Any]:
        session = await self._session_or_create()
        async with session.post(f"{self._config.base_url}{path}", json=json_payload) as response:
            payload = _parse_payload(await response.text(), status=response.status)
            if response.status >= 400:
                raise RuntimeError(str(payload.get("error") or payload))
            return payload

    async def _session_or_create(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._config.timeout_seconds)
            )
        return self._session


class _MemoryMutationOps:
    """Mutation operations: remember, delete, clear."""

    def __init__(self, transport: _MemoryTransport) -> None:
        self._transport = transport

    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, Any]:
        payload = await self._transport.request(
            path="/memory/remember",
            json_payload={
                "agent_slug": agent_slug,
                "room": room,
                "category": category,
                "text": text,
            },
        )
        return dict(payload.get("memory") or {})

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool:
        payload = await self._transport.request(
            path="/memory/delete",
            json_payload={
                "agent_slug": agent_slug,
                "memory_id": memory_id,
            },
        )
        return bool(payload.get("deleted"))

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int:
        payload = await self._transport.request(
            path="/memory/clear",
            json_payload={
                "agent_slug": agent_slug,
                "room": room,
                "category": category,
            },
        )
        return int(payload.get("deleted_count") or 0)


class _MemoryQueryOps:
    """Query operations: search, list_rooms, list_categories."""

    def __init__(self, transport: _MemoryTransport) -> None:
        self._transport = transport

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        payload = await self._transport.request(
            path="/memory/search",
            json_payload={
                "agent_slug": agent_slug,
                "query": query,
                "room": room,
                "category": category,
                "limit": limit,
            },
        )
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [dict(item) for item in items if isinstance(item, dict)]

    async def list_rooms(self, *, agent_slug: str) -> list[str]:
        payload = await self._transport.request(
            path="/memory/discovery/rooms",
            json_payload={"agent_slug": agent_slug},
        )
        rooms = payload.get("rooms")
        if not isinstance(rooms, list):
            return []
        return [str(r) for r in rooms if isinstance(r, str)]

    async def list_categories(self, *, agent_slug: str) -> list[str]:
        payload = await self._transport.request(
            path="/memory/discovery/categories",
            json_payload={"agent_slug": agent_slug},
        )
        categories = payload.get("categories")
        if not isinstance(categories, list):
            return []
        return [str(c) for c in categories if isinstance(c, str)]


class OrchestraMemoryClient:  # noqa: WPS214 (cohesive HTTP client facade)
    """Public client delegating to mutation and query operation classes."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        config = _build_config(base_url=base_url, timeout_seconds=timeout_seconds)
        transport = _MemoryTransport(config=config)
        self._mutations = _MemoryMutationOps(transport=transport)
        self._queries = _MemoryQueryOps(transport=transport)

    async def close(self) -> None:
        await self._mutations._transport.close()  # noqa: SLF001  # Shared transport reference

    # -- Mutation delegation --

    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, Any]:
        return await self._mutations.remember(
            agent_slug=agent_slug,
            room=room,
            category=category,
            text=text,
        )

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool:
        return await self._mutations.delete(agent_slug=agent_slug, memory_id=memory_id)

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int:
        return await self._mutations.clear(
            agent_slug=agent_slug,
            room=room,
            category=category,
        )

    # -- Query delegation --

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await self._queries.search(
            agent_slug=agent_slug,
            query=query,
            room=room,
            category=category,
            limit=limit,
        )

    async def list_rooms(self, *, agent_slug: str) -> list[str]:
        return await self._queries.list_rooms(agent_slug=agent_slug)

    async def list_categories(self, *, agent_slug: str) -> list[str]:
        return await self._queries.list_categories(agent_slug=agent_slug)


def _build_config(*, base_url: str | None, timeout_seconds: float | None) -> _MemoryClientConfig:
    resolved_base_url = str(
        base_url or os.getenv("ORCHESTRA_MEMORY_URL") or "http://127.0.0.1:8793"
    ).rstrip("/")
    resolved_timeout = timeout_seconds
    if resolved_timeout is None:
        resolved_timeout = float(os.getenv("ORCHESTRA_MEMORY_HTTP_TIMEOUT_SECONDS", "10"))
    return _MemoryClientConfig(
        base_url=resolved_base_url,
        timeout_seconds=max(1.0, float(resolved_timeout)),
    )


def _parse_payload(raw_body: str, *, status: int) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        if status >= 400:
            raise RuntimeError(raw_body.strip() or f"HTTP {status}") from None
        raise RuntimeError(
            f"orchestra_memory returned a non-JSON response with HTTP {status}"
        ) from None
    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError("orchestra_memory returned a non-object response")
