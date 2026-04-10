from __future__ import annotations

import asyncio
import inspect
import json
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any, Self, cast

from aiohttp import ClientSession, ClientTimeout, web

from core.orchestra_thread.service_runtime_config import RuntimeConfigOverrides

thread_service_runtime = import_module("core.orchestra_thread.service.runtime")
OrchestraThreadsService = cast(type[Any], thread_service_runtime.OrchestraThreadsService)
build_app = thread_service_runtime.build_app


_HTTP_SERVICE_UNAVAILABLE = 503
_HTTP_OK = 200
_METHOD_POST = "POST"
_METHOD_GET = "GET"
_AGENT_LEASE_SECONDS = 30
_DELIVERY_POLL_SECONDS = 0.2


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class FakeAgent:
    def __init__(self, slug: str, port: int | None = None) -> None:
        self.slug = slug
        self.port = port or free_port()
        self.runner: web.AppRunner | None = None
        self.events: list[dict[str, Any]] = []
        self.stops: list[dict[str, Any]] = []
        self.fail_event_delivery = False

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> None:
        if self.runner is not None:
            return
        app = web.Application()
        app.router.add_post("/event", self._handle_event)
        app.router.add_post("/stop", self._handle_stop)
        app.router.add_get("/healthz", self._handle_healthz)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()

    async def stop(self) -> None:
        if self.runner is None:
            return
        await self.runner.cleanup()
        self.runner = None

    async def _handle_event(self, request: web.Request) -> web.Response:
        if self.fail_event_delivery:
            return web.json_response(
                {"accepted": False, "error": "forced failure"}, status=_HTTP_SERVICE_UNAVAILABLE
            )
        payload = await request.json()
        self.events.extend(payload.get("events") or [])
        return web.json_response(
            {"accepted": True, "event_count": len(payload.get("events") or [])}
        )

    async def _handle_stop(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.stops.append(payload)
        return web.json_response({"accepted": True})

    async def _handle_healthz(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "agent_slug": self.slug})


class HarnessRequestHelpers:
    session: ClientSession | None
    base_url: str | None

    async def request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        expected_status: int = _HTTP_OK,
    ) -> dict[str, Any]:
        assert self.session is not None
        assert self.base_url is not None
        async with self.session.request(method, f"{self.base_url}{path}", json=payload) as response:
            raw = await response.text()
            parsed = json.loads(raw) if raw else {}
            if response.status != expected_status:
                raise AssertionError(
                    f"{method} {path} returned {response.status}, expected {expected_status}: {parsed}"
                )
            return cast(dict[str, Any], parsed)

    async def request_text(
        self,
        *,
        method: str,
        path: str,
        expected_status: int = _HTTP_OK,
    ) -> tuple[str, str]:
        assert self.session is not None
        assert self.base_url is not None
        async with self.session.request(method, f"{self.base_url}{path}") as response:
            raw = await response.text()
            if response.status != expected_status:
                raise AssertionError(
                    f"{method} {path} returned {response.status}, expected {expected_status}: {raw}"
                )
            return raw, str(response.headers.get("Content-Type") or "")


class HarnessApiHelpers(HarnessRequestHelpers):
    async def send_message(
        self,
        payload: dict[str, Any],
        *,
        expected_status: int = _HTTP_OK,
    ) -> dict[str, Any]:
        return await self.request_json(
            method=_METHOD_POST,
            path="/api/v1/messages",
            payload=payload,
            expected_status=expected_status,
        )

    async def send_notification(
        self,
        payload: dict[str, Any],
        *,
        expected_status: int = _HTTP_OK,
    ) -> dict[str, Any]:
        return await self.request_json(
            method=_METHOD_POST,
            path="/api/v1/notifications",
            payload=payload,
            expected_status=expected_status,
        )

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        return await self.request_json(method=_METHOD_GET, path=f"/api/v1/threads/{thread_id}")

    async def list_agents(self) -> dict[str, Any]:
        return await self.request_json(method=_METHOD_GET, path="/agents")

    async def get_agent_status(self, agent_slug: str) -> dict[str, Any]:
        return await self.request_json(method="GET", path=f"/agents/{agent_slug}/status")

    async def list_threads(self, *, scope: str = "active") -> dict[str, Any]:
        return await self.request_json(method=_METHOD_GET, path=f"/api/v1/threads?scope={scope}")

    async def get_instruction(
        self,
        *,
        view: str = "compact",
        section: str | None = None,
    ) -> dict[str, Any]:
        path = f"/api/v1/instructions?view={view}"
        if section:
            path = f"{path}&section={section}"
        return await self.request_json(method=_METHOD_GET, path=path)


class HarnessAgentHelpers(HarnessApiHelpers):
    agents: list[FakeAgent]

    async def add_agent(self, slug: str) -> FakeAgent:
        agent = FakeAgent(slug=slug)
        await agent.start()
        await self.register_agent(agent)
        self.agents.append(agent)
        return agent

    async def register_agent(self, agent: FakeAgent) -> dict[str, Any]:
        return await self.request_json(
            method=_METHOD_POST,
            path="/agents/register",
            payload={"agent_slug": agent.slug, "base_url": agent.base_url},
        )

    async def heartbeat(self, slug: str) -> dict[str, Any]:
        return await self.request_json(
            method=_METHOD_POST,
            path="/agents/heartbeat",
            payload={"agent_slug": slug},
        )


class HarnessLifecycleHelpers(HarnessAgentHelpers):
    service: Any
    app_runner: web.AppRunner | None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    async def start(self) -> None:
        await self.service.start()
        app = build_app(self.service)
        self.app_runner = web.AppRunner(app)
        await self.app_runner.setup()
        port = free_port()
        await web.TCPSite(self.app_runner, host="127.0.0.1", port=port).start()
        self.base_url = f"http://127.0.0.1:{port}"
        self.session = ClientSession(timeout=ClientTimeout(total=10))

    async def stop(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None
        await self._stop_agents()
        self.agents.clear()
        if self.app_runner is not None:
            await self.app_runner.cleanup()
            self.app_runner = None
        await self.service.stop()
        await self.service.drop_storage()

    async def wait_for(
        self,
        predicate: Callable[[], Any] | Callable[[], Awaitable[Any]],
        *,
        timeout: float = 5.0,
        interval: float = 0.05,
        message: str,
    ) -> Any:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            check_result = predicate()
            if inspect.isawaitable(check_result):
                check_result = await check_result
            if check_result:
                return check_result
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError(message)
            await asyncio.sleep(interval)

    async def close_thread(
        self,
        *,
        owner_agent: FakeAgent,
        peer_agent: FakeAgent,
        thread_id: str,
        message_text: str = "Closing test thread.",
    ) -> dict[str, Any]:
        stop_count_before = len(peer_agent.stops)
        payload = await self.send_notification(
            {
                "from_agent_slug": owner_agent.slug,
                "to_agent_slug": peer_agent.slug,
                "thread_id": thread_id,
                "status": "closed",
                "message_text": message_text,
            }
        )
        await self.wait_for(
            lambda: len(peer_agent.stops) > stop_count_before,
            message=f"{peer_agent.slug} did not receive stop after closing test thread {thread_id}",
        )
        return payload

    async def _stop_agents(self) -> None:
        stop_tasks = [agent.stop() for agent in reversed(self.agents)]
        await asyncio.gather(*stop_tasks)


class E2EHarness(HarnessLifecycleHelpers):
    def __init__(self, *, database_url: str | None = None) -> None:
        hex_suffix = uuid.uuid4().hex
        self.schema_name = f"test_{hex_suffix}"
        self.service = cast(
            Any,
            OrchestraThreadsService(
                runtime_config_overrides=RuntimeConfigOverrides(
                    database_url=(
                        database_url
                        or os.getenv("ORCHESTRA_THREADS_TEST_DATABASE_URL")
                        or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
                        or "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads"
                    ),
                    database_schema=self.schema_name,
                    db_min_pool_size=1,
                    db_max_pool_size=4,
                    agent_lease_seconds=_AGENT_LEASE_SECONDS,
                    delivery_poll_interval_seconds=_DELIVERY_POLL_SECONDS,
                    inactivity_timeout_seconds=10,
                    retry_base_seconds=1,
                    retry_max_seconds=2,
                ),
            ),
        )
        self.service.delivery_poll_interval_seconds = 0.1
        self.service.inactivity_timeout_seconds = 2
        self.app_runner: web.AppRunner | None = None
        self.base_url: str | None = None
        self.session: ClientSession | None = None
        self.agents: list[FakeAgent] = []
