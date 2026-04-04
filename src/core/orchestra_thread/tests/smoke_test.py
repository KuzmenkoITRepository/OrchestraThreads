"""Basic end-to-end smoke test for the OrchestraThreads MVP."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

import aiohttp
from aiohttp import web

from core.orchestra_thread.service import OrchestraThreadsService, build_app


class FakeAgent:
    def __init__(self, slug: str, port: int) -> None:
        self.slug = slug
        self.port = port
        self.runner: web.AppRunner | None = None
        self.events: list[dict[str, Any]] = []
        self.stops: list[dict[str, Any]] = []

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/event", self._handle_event)
        app.router.add_post("/stop", self._handle_stop)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _handle_event(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.events.extend(payload.get("events") or [])
        return web.json_response({"accepted": True})

    async def _handle_stop(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.stops.append(payload)
        return web.json_response({"accepted": True})


async def main() -> None:
    service = OrchestraThreadsService(
        database_url=(
            os.getenv("ORCHESTRA_THREADS_TEST_DATABASE_URL")
            or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
            or "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads"
        ),
        database_schema=f"smoke_{uuid.uuid4().hex}",
        db_min_pool_size=1,
        db_max_pool_size=2,
        delivery_poll_interval_seconds=0.2,
        inactivity_timeout_seconds=4,
        retry_base_seconds=1,
        retry_max_seconds=2,
    )
    await service.start()
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host="127.0.0.1", port=8789).start()

    agent_a = FakeAgent("secretary", 9791)
    agent_b = FakeAgent("orchestra", 9792)
    await agent_a.start()
    await agent_b.start()

    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    try:
        for slug, port in (("secretary", 9791), ("orchestra", 9792)):
            async with session.post(
                "http://127.0.0.1:8789/agents/register",
                json={
                    "agent_slug": slug,
                    "base_url": f"http://127.0.0.1:{port}",
                },
            ) as response:
                assert response.status == 200, await response.text()

        async with session.post(
            "http://127.0.0.1:8789/api/v1/messages",
            json={
                "from_agent_slug": "secretary",
                "to_agent_slug": "orchestra",
                "message_text": "Prepare a short update.",
            },
        ) as response:
            body = await response.json()
            assert response.status == 200, body
            thread_id = str(body["thread"]["thread_id"])

        for _ in range(20):
            if agent_b.events:
                break
            await asyncio.sleep(0.2)
        assert agent_b.events, "orchestra did not receive the initial message"

        async with session.post(
            "http://127.0.0.1:8789/api/v1/messages",
            json={
                "from_agent_slug": "orchestra",
                "to_agent_slug": "secretary",
                "thread_id": thread_id,
                "message_text": "Done. Here is the update.",
            },
        ) as response:
            body = await response.json()
            assert response.status == 200, body

        for _ in range(20):
            if agent_a.events:
                break
            await asyncio.sleep(0.2)
        assert agent_a.events, "secretary did not receive the reply"

        async with session.get(f"http://127.0.0.1:8789/api/v1/threads/{thread_id}") as response:
            body = await response.json()
            assert response.status == 200, body
            assert len(body["events"]) == 2, body

        print(
            json.dumps(
                {
                    "ok": True,
                    "thread_id": thread_id,
                    "secretary_events": len(agent_a.events),
                    "orchestra_events": len(agent_b.events),
                },
                ensure_ascii=False,
            )
        )
    finally:
        await session.close()
        await agent_a.stop()
        await agent_b.stop()
        await runner.cleanup()
        await service.stop()
        await service.drop_storage()


if __name__ == "__main__":
    asyncio.run(main())
