from __future__ import annotations

import asyncio
import unittest
from typing import Any

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.telegram_events.relay_compat_http import build_relay_compat_app


class _FakeRelayService:
    def __init__(self) -> None:
        self.mcp_requests: list[dict[str, Any]] = []

    def subscribe(self) -> asyncio.Queue[str | None]:
        subscriber: asyncio.Queue[str | None] = asyncio.Queue()
        subscriber.put_nowait(
            '{"event_id":"evt-1","event_type":"message","occurred_at":"2024-01-01T00:00:00Z","mode":"private","account":"telegram","update":{"message":{"id":1}}}'
        )
        subscriber.put_nowait(None)
        return subscriber

    def unsubscribe(self, subscriber: asyncio.Queue[str | None]) -> None:
        subscriber.put_nowait(None)

    async def handle_json_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.mcp_requests.append(payload)
        return {"jsonrpc": "2.0", "id": payload.get("id", 1), "result": {"ok": True}}


class RelayCompatHttpTests(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self._service = _FakeRelayService()
        return build_relay_compat_app(self._service, "secret-token")

    async def test_health_returns_ok(self) -> None:
        response = await self.client.get("/health")

        self.assertEqual(response.status, 200)
        self.assertEqual(
            await response.json(),
            {"ok": True, "service": "better-telegram-mcp"},
        )

    async def test_events_require_bearer_token(self) -> None:
        response = await self.client.get("/events/telegram")

        self.assertEqual(response.status, 401)

    async def test_events_stream_payloads(self) -> None:
        response = await self.client.get(
            "/events/telegram",
            headers={"Authorization": "Bearer secret-token"},
        )

        self.assertEqual(response.status, 200)
        self.assertIn('data: {"event_id":"evt-1"', await response.text())

    async def test_mcp_requires_bearer_token(self) -> None:
        response = await self.client.post("/mcp", json={"method": "tools/call"})

        self.assertEqual(response.status, 401)
        self.assertEqual(await response.json(), {"error": "Unauthorized"})

    async def test_mcp_forwards_json_rpc(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {}}

        response = await self.client.post(
            "/mcp",
            headers={"Authorization": "Bearer secret-token"},
            json=payload,
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(self._service.mcp_requests, [payload])


if __name__ == "__main__":
    unittest.main()
