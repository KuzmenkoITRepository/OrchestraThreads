from __future__ import annotations

import unittest
from dataclasses import dataclass

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.telegram_events import http_server
from core.telegram_events.agent_registry import TelegramAgentRegistry


@dataclass
class _RegisterCall:
    agent_slug: str
    telegram_mcp_url: str


async def _register_agent(
    test_case: TelegramEventsHttpServerTests,
    agent_registry: TelegramAgentRegistry,
    agent_slug: str,
    telegram_mcp_url: str,
) -> object:
    test_case.assertIs(agent_registry, test_case.registry)
    test_case.register_calls.append(_RegisterCall(agent_slug, telegram_mcp_url))
    return agent_registry.register(agent_slug, telegram_mcp_url)


class TelegramEventsHttpServerTests(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        app = http_server.build_app()
        self.registry = TelegramAgentRegistry()
        self.register_calls: list[_RegisterCall] = []
        app["agent_registry"] = self.registry
        app["register_agent"] = lambda agent_registry, agent_slug, telegram_mcp_url: (
            _register_agent(
                self,
                agent_registry,
                agent_slug,
                telegram_mcp_url,
            )
        )
        return app

    async def test_build_app_exposes_only_healthz_and_register(self) -> None:
        routes = sorted(
            str(route.resource.get_info().get("path"))
            for route in self.app.router.routes()
            if route.resource is not None
        )

        self.assertEqual(sorted(set(routes)), ["/healthz", "/register"])

    async def test_send_route_is_not_registered(self) -> None:
        response = await self.client.post(
            "/send",
            json={"chat_id": 1, "message": "hello"},
        )

        self.assertEqual(response.status, 404)

    async def test_register_creates_agent_with_exact_ok_response(self) -> None:
        response = await self.client.post(
            "/register",
            json={
                "agent_slug": "assistant-alpha",
                "telegram_mcp_url": "http://relay.test/mcp",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"ok": True})
        self.assertEqual(
            self.register_calls, [_RegisterCall("assistant-alpha", "http://relay.test/mcp")]
        )

    async def test_register_is_idempotent_for_duplicate_payload(self) -> None:
        payload = {
            "agent_slug": "assistant-alpha",
            "telegram_mcp_url": "http://relay.test/mcp",
        }

        first = await self.client.post("/register", json=payload)
        second = await self.client.post("/register", json=payload)

        self.assertEqual(first.status, 200)
        self.assertEqual(await first.json(), {"ok": True})
        self.assertEqual(second.status, 200)
        self.assertEqual(await second.json(), {"ok": True})

    async def test_register_allows_same_slug_update_to_new_url(self) -> None:
        first = await self.client.post(
            "/register",
            json={
                "agent_slug": "assistant-alpha",
                "telegram_mcp_url": "http://relay.test/mcp",
            },
        )
        second = await self.client.post(
            "/register",
            json={
                "agent_slug": "assistant-alpha",
                "telegram_mcp_url": "http://relay-two.test/mcp",
            },
        )

        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(await second.json(), {"ok": True})

    async def test_register_rejects_conflicting_url_ownership(self) -> None:
        first = await self.client.post(
            "/register",
            json={
                "agent_slug": "assistant-alpha",
                "telegram_mcp_url": "http://relay.test/mcp",
            },
        )
        conflict = await self.client.post(
            "/register",
            json={
                "agent_slug": "assistant-bravo",
                "telegram_mcp_url": "http://relay.test/mcp/",
            },
        )

        self.assertEqual(first.status, 200)
        self.assertEqual(conflict.status, 409)
        self.assertEqual(
            await conflict.json(), {"ok": False, "error": "telegram_mcp_url already registered"}
        )

    async def test_register_rejects_invalid_json(self) -> None:
        response = await self.client.post(
            "/register",
            data="not-json",
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status, 400)

    async def test_register_rejects_missing_fields(self) -> None:
        response = await self.client.post(
            "/register",
            json={"agent_slug": "assistant-alpha"},
        )

        self.assertEqual(response.status, 400)

    async def test_register_rejects_non_string_fields(self) -> None:
        response = await self.client.post(
            "/register",
            json={"agent_slug": 123, "telegram_mcp_url": "http://relay.test/mcp"},
        )

        self.assertEqual(response.status, 400)

    async def test_register_rejects_empty_values(self) -> None:
        response = await self.client.post(
            "/register",
            json={"agent_slug": " ", "telegram_mcp_url": "http://relay.test/mcp"},
        )

        self.assertEqual(response.status, 400)

    async def test_register_rejects_invalid_url_shape(self) -> None:
        response = await self.client.post(
            "/register",
            json={"agent_slug": "assistant-alpha", "telegram_mcp_url": "ftp://relay.test/mcp"},
        )

        self.assertEqual(response.status, 400)


if __name__ == "__main__":
    unittest.main()
