from __future__ import annotations

import json
import socket
import unittest
from typing import Any

import aiohttp

from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    EventDelivery,
    EventDeliveryResult,
    StandardAgentApplication,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class DummyBackend(BaseAgentBackend):
    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        self.remember_delivery(delivery)
        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=delivery.delivery_id,
        )


class RuntimeContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.backend = DummyBackend(
            agent_slug="dummy_agent",
            backend_type="example",
            working_dir="/workspace",
        )
        self.port = _free_port()
        self.app = StandardAgentApplication(backend=self.backend, host="127.0.0.1", port=self.port)
        await self.app.start()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.app.stop()

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with self.session.request(
            method, f"http://127.0.0.1:{self.port}{path}", json=payload
        ) as response:
            raw = await response.text()
            data = json.loads(raw) if raw else {}
            if response.status >= 400:
                raise AssertionError(f"{method} {path} -> {response.status}: {data}")
            return data

    async def test_runtime_contract_endpoints(self) -> None:
        health = await self._request("GET", "/healthz")
        self.assertEqual(health["status"], "ok")
        initial_context_id = health["context_id"]
        self.assertTrue(initial_context_id)

        event_result = await self._request(
            "POST",
            "/event",
            {
                "delivery_id": "delivery-1",
                "events": [
                    {
                        "event_id": "event-1",
                        "thread_id": "thread-1",
                        "event_kind": "message",
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "dummy_agent",
                        "message_text": "Ping",
                    }
                ],
            },
        )
        self.assertTrue(event_result["accepted"])
        self.assertEqual(event_result["accepted_events"], 1)

        status = await self._request("GET", "/last_status")
        self.assertEqual(status["last_delivery_id"], "delivery-1")
        self.assertEqual(status["last_event_kind"], "message")
        self.assertEqual(status["context_id"], initial_context_id)

        clear_result = await self._request("POST", "/clear_context", {"requested_by": "service"})
        self.assertTrue(clear_result["success"])
        self.assertEqual(clear_result["context_generation"], 1)
        self.assertEqual(clear_result["previous_context_id"], initial_context_id)
        self.assertNotEqual(clear_result["context_id"], initial_context_id)

        stop_result = await self._request("POST", "/stop", {"reason": "closed"})
        self.assertTrue(stop_result["success"])
        self.assertEqual(stop_result["stop_reason"], "closed")
