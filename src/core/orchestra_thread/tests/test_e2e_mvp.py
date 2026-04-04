"""End-to-end coverage for the main OrchestraThreads MVP scenarios."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import socket
import unittest
import uuid
from typing import Any, Optional

import aiohttp
from aiohttp import web

from core.orchestra_thread.service import OrchestraThreadsService, build_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class FakeAgent:
    """Small callback-capable agent used by the e2e tests."""

    def __init__(self, slug: str, port: Optional[int] = None) -> None:
        self.slug = slug
        self.port = port or _free_port()
        self.runner: Optional[web.AppRunner] = None
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

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def _handle_event(self, request: web.Request) -> web.Response:
        if self.fail_event_delivery:
            return web.json_response({"accepted": False, "error": "forced failure"}, status=503)
        payload = await request.json()
        self.events.extend(payload.get("events") or [])
        return web.json_response({"accepted": True, "event_count": len(payload.get("events") or [])})

    async def _handle_stop(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.stops.append(payload)
        return web.json_response({"accepted": True})

    async def _handle_healthz(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "agent_slug": self.slug})


class E2EHarness:
    """Owns a test-local service, HTTP client, and helper methods."""

    def __init__(self) -> None:
        self.schema_name = f"test_{uuid.uuid4().hex}"
        self.service = OrchestraThreadsService(
            database_url=(
                os.getenv("ORCHESTRA_THREADS_TEST_DATABASE_URL")
                or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
                or "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads"
            ),
            database_schema=self.schema_name,
            db_min_pool_size=1,
            db_max_pool_size=4,
            agent_lease_seconds=30,
            delivery_poll_interval_seconds=0.2,
            inactivity_timeout_seconds=10,
            retry_base_seconds=1,
            retry_max_seconds=2,
        )
        self.service.delivery_poll_interval_seconds = 0.1
        self.service.inactivity_timeout_seconds = 2
        self.app_runner: Optional[web.AppRunner] = None
        self.base_url: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.agents: list[FakeAgent] = []

    async def start(self) -> None:
        await self.service.start()
        app = build_app(self.service)
        self.app_runner = web.AppRunner(app)
        await self.app_runner.setup()
        port = _free_port()
        await web.TCPSite(self.app_runner, host="127.0.0.1", port=port).start()
        self.base_url = f"http://127.0.0.1:{port}"
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def stop(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None
        for agent in reversed(self.agents):
            await agent.stop()
        self.agents.clear()
        if self.app_runner is not None:
            await self.app_runner.cleanup()
            self.app_runner = None
        await self.service.stop()
        await self.service.drop_storage()

    async def add_agent(self, slug: str) -> FakeAgent:
        agent = FakeAgent(slug=slug)
        await agent.start()
        await self.register_agent(agent)
        self.agents.append(agent)
        return agent

    async def register_agent(self, agent: FakeAgent) -> dict[str, Any]:
        return await self.request_json(
            method="POST",
            path="/agents/register",
            payload={
                "agent_slug": agent.slug,
                "base_url": agent.base_url,
            },
        )

    async def heartbeat(self, slug: str) -> dict[str, Any]:
        return await self.request_json(
            method="POST",
            path="/agents/heartbeat",
            payload={"agent_slug": slug},
        )

    async def request_json(
        self,
        *,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        assert self.session is not None
        assert self.base_url is not None
        async with self.session.request(method, f"{self.base_url}{path}", json=payload) as response:
            raw = await response.text()
            data = json.loads(raw) if raw else {}
            if response.status != expected_status:
                raise AssertionError(
                    f"{method} {path} returned {response.status}, expected {expected_status}: {data}"
                )
            return data

    async def request_text(
        self,
        *,
        method: str,
        path: str,
        expected_status: int = 200,
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

    async def send_message(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        thread_id: Optional[str] = None,
        parent_thread_id: Optional[str] = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        payload = {
            "from_agent_slug": from_agent_slug,
            "to_agent_slug": to_agent_slug,
            "message_text": message_text,
        }
        if thread_id is not None:
            payload["thread_id"] = thread_id
        if parent_thread_id is not None:
            payload["parent_thread_id"] = parent_thread_id
        return await self.request_json(
            method="POST",
            path="/api/v1/messages",
            payload=payload,
            expected_status=expected_status,
        )

    async def send_notification(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        thread_id: str,
        status: str,
        message_text: str,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        return await self.request_json(
            method="POST",
            path="/api/v1/notifications",
            payload={
                "from_agent_slug": from_agent_slug,
                "to_agent_slug": to_agent_slug,
                "thread_id": thread_id,
                "status": status,
                "message_text": message_text,
            },
            expected_status=expected_status,
        )

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
            from_agent_slug=owner_agent.slug,
            to_agent_slug=peer_agent.slug,
            thread_id=thread_id,
            status="closed",
            message_text=message_text,
        )
        await self.wait_for(
            lambda: len(peer_agent.stops) > stop_count_before,
            message=f"{peer_agent.slug} did not receive stop after closing test thread {thread_id}",
        )
        return payload

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        return await self.request_json(method="GET", path=f"/api/v1/threads/{thread_id}")

    async def list_agents(self) -> dict[str, Any]:
        return await self.request_json(method="GET", path="/agents")

    async def list_threads(self, *, scope: str = "active") -> dict[str, Any]:
        return await self.request_json(method="GET", path=f"/api/v1/threads?scope={scope}")

    async def get_instruction(self, *, view: str = "compact", section: Optional[str] = None) -> dict[str, Any]:
        path = f"/api/v1/instructions?view={view}"
        if section:
            path += f"&section={section}"
        return await self.request_json(method="GET", path=path)

    async def wait_for(
        self,
        predicate,
        *,
        timeout: float = 5.0,
        interval: float = 0.05,
        message: str,
    ) -> Any:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            value = predicate()
            if inspect.isawaitable(value):
                value = await value
            if value:
                return value
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError(message)
            await asyncio.sleep(interval)


class OrchestraThreadsE2ETestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.harness = E2EHarness()
        await self.harness.start()

    async def asyncTearDown(self) -> None:
        await self.harness.stop()

    async def test_registration_and_heartbeat_report_agents_online(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")

        agents_payload = await self.harness.list_agents()
        online_map = {
            item["agent_slug"]: bool(item["online"])
            for item in agents_payload["agents"]
        }
        self.assertTrue(online_map.get(secretary.slug))
        self.assertTrue(online_map.get(orchestra.slug))

        before = next(item for item in agents_payload["agents"] if item["agent_slug"] == secretary.slug)["last_seen_at"]
        await asyncio.sleep(0.02)
        heartbeat_payload = await self.harness.heartbeat(secretary.slug)
        after = heartbeat_payload["agent"]["last_seen_at"]
        self.assertNotEqual(before, after)
        self.assertTrue(heartbeat_payload["agent"]["online"])

    async def test_root_thread_create_reply_and_reuse(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")

        initial = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Prepare a short update.",
        )
        root_thread_id = str(initial["thread"]["thread_id"])
        self.assertTrue(initial["created_thread"])

        await self.harness.wait_for(
            lambda: len(orchestra.events) >= 1,
            message="orchestra did not receive the initial root-thread message",
        )
        self.assertEqual(orchestra.events[-1]["thread_id"], root_thread_id)

        reply = await self.harness.send_message(
            from_agent_slug=orchestra.slug,
            to_agent_slug=secretary.slug,
            thread_id=root_thread_id,
            message_text="Done. Here is the update.",
        )
        self.assertEqual(reply["thread"]["thread_id"], root_thread_id)

        await self.harness.wait_for(
            lambda: len(secretary.events) >= 1,
            message="secretary did not receive the reply on the root thread",
        )
        self.assertEqual(secretary.events[-1]["thread_id"], root_thread_id)

        reused = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="One more thing.",
        )
        self.assertFalse(reused["created_thread"])
        self.assertEqual(reused["thread"]["thread_id"], root_thread_id)

        threads_payload = await self.harness.list_threads(scope="active")
        active_roots = [item for item in threads_payload["threads"] if item["scope"] == "root"]
        self.assertEqual(len(active_roots), 1)
        self.assertEqual(active_roots[0]["thread_id"], root_thread_id)

        closed = await self.harness.close_thread(
            owner_agent=secretary,
            peer_agent=orchestra,
            thread_id=root_thread_id,
            message_text="Closing root test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

    async def test_ui_root_serves_thread_console(self) -> None:
        body, content_type = await self.harness.request_text(method="GET", path="/")
        self.assertIn("Thread Service Console", body)
        self.assertIn("OrchestraThreads", body)
        self.assertIn("/static/thread-service-ui.js", body)
        self.assertIn("text/html", content_type)

    async def test_thread_payloads_are_ui_enriched(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")

        initial = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Prepare a short update.",
        )
        thread_id = str(initial["thread"]["thread_id"])

        await self.harness.wait_for(
            lambda: len(orchestra.events) >= 1,
            message="orchestra did not receive the initial root-thread message for UI payload test",
        )

        async def _thread_ready() -> Any:
            threads_payload = await self.harness.list_threads(scope="active")
            thread = next((item for item in threads_payload["threads"] if item["thread_id"] == thread_id), None)
            if not thread:
                return None
            if thread.get("pending_delivery_count") != 0:
                return None
            if not thread.get("last_event"):
                return None
            return thread

        thread = await self.harness.wait_for(
            _thread_ready,
            message="thread summary did not reach the enriched UI-ready state",
        )
        self.assertEqual(thread["thread_scope"], "root")
        self.assertEqual(thread["event_count"], 1)
        self.assertEqual(thread["pending_delivery_count"], 0)
        self.assertEqual(thread["child_thread_count"], 0)
        self.assertEqual(thread["agents"]["owner"]["slug"], secretary.slug)
        self.assertEqual(thread["agents"]["peer"]["slug"], orchestra.slug)
        self.assertEqual(thread["roles"]["peer_agent_slug"], orchestra.slug)
        self.assertIn("secretary", thread["pair_label"])
        self.assertIn("orchestra", thread["pair_label"])
        self.assertEqual(thread["last_event"]["message_preview"], "Prepare a short update.")

        detail = await self.harness.get_thread(thread_id)
        self.assertEqual(detail["thread"]["thread_scope"], "root")
        self.assertEqual(detail["thread"]["event_count"], 1)
        self.assertEqual(detail["thread"]["pending_delivery_count"], 0)
        self.assertEqual(detail["thread"]["child_thread_count"], 0)
        self.assertEqual(detail["thread"]["last_event"]["message_preview"], "Prepare a short update.")
        self.assertEqual(detail["events"][0]["from_agent"]["slug"], secretary.slug)
        self.assertEqual(detail["events"][0]["to_agent"]["slug"], orchestra.slug)
        self.assertTrue(detail["events"][0]["requires_action"])
        self.assertTrue(detail["events"][0]["requires_response"])
        self.assertEqual(detail["events"][0]["message_preview"], "Prepare a short update.")
        self.assertEqual(detail["related"]["root_thread"]["thread_id"], thread_id)

        closed = await self.harness.close_thread(
            owner_agent=secretary,
            peer_agent=orchestra,
            thread_id=thread_id,
            message_text="Closing UI payload test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

    async def test_message_text_sanitizes_terminal_garbage(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")

        initial = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Привет! \udcd0Кто ты?",
        )
        thread_id = str(initial["thread"]["thread_id"])

        await self.harness.wait_for(
            lambda: len(orchestra.events) >= 1,
            message="orchestra did not receive the sanitized message",
        )

        self.assertEqual(orchestra.events[-1]["message_text"], "Привет! Кто ты?")
        detail = await self.harness.get_thread(thread_id)
        self.assertEqual(detail["events"][0]["message_text"], "Привет! Кто ты?")

        closed = await self.harness.close_thread(
            owner_agent=secretary,
            peer_agent=orchestra,
            thread_id=thread_id,
            message_text="Closing sanitize-message test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

    async def test_instruction_endpoint_returns_compact_workflow(self) -> None:
        payload = await self.harness.get_instruction()
        instruction = payload["instruction"]
        self.assertEqual(instruction["instruction_id"], "orchestra_threads_mvp")
        self.assertEqual(instruction["view"], "compact")
        self.assertEqual(instruction["section"], "all")
        self.assertIn("workflow", instruction)
        self.assertIn("routing_rules", instruction)
        self.assertIn("thread_send", instruction["text"])

        routing_payload = await self.harness.get_instruction(section="routing")
        routing_instruction = routing_payload["instruction"]
        self.assertEqual(routing_instruction["section"], "routing")
        self.assertIn("routing_rules", routing_instruction)
        self.assertNotIn("status_rules", routing_instruction)

    async def test_status_permissions_terminal_close_and_stop(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")

        initial = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Prepare a short update.",
        )
        thread_id = str(initial["thread"]["thread_id"])
        await self.harness.wait_for(
            lambda: len(orchestra.events) >= 1,
            message="orchestra did not receive the initial message",
        )

        review = await self.harness.send_notification(
            from_agent_slug=orchestra.slug,
            to_agent_slug=secretary.slug,
            thread_id=thread_id,
            status="review",
            message_text="Ready for handoff.",
        )
        self.assertEqual(review["thread"]["status"], "review")

        await self.harness.wait_for(
            lambda: any(event.get("notification_status") == "review" for event in secretary.events),
            message="secretary did not receive the review notification",
        )

        invalid_done = await self.harness.send_notification(
            from_agent_slug=orchestra.slug,
            to_agent_slug=secretary.slug,
            thread_id=thread_id,
            status="done",
            message_text="Done.",
            expected_status=409,
        )
        self.assertIn("cannot publish done", invalid_done["error"])

        closed = await self.harness.send_notification(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            thread_id=thread_id,
            status="closed",
            message_text="Closing thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

        await self.harness.wait_for(
            lambda: len(orchestra.stops) >= 1,
            message="orchestra did not receive stop after thread closure",
        )
        self.assertEqual(orchestra.stops[-1]["thread_id"], thread_id)

        after_close = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            thread_id=thread_id,
            message_text="Should fail after close.",
            expected_status=409,
        )
        self.assertIn("already terminal", after_close["error"])

    async def test_child_thread_creation_and_parent_close_cascades(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")
        specialist = await self.harness.add_agent("specialist")

        root = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Coordinate a specialist.",
        )
        root_thread_id = str(root["thread"]["thread_id"])
        await self.harness.wait_for(
            lambda: len(orchestra.events) >= 1,
            message="orchestra did not receive the root-thread message",
        )

        child = await self.harness.send_message(
            from_agent_slug=orchestra.slug,
            to_agent_slug=specialist.slug,
            parent_thread_id=root_thread_id,
            message_text="Check one detail.",
        )
        child_thread_id = str(child["thread"]["thread_id"])
        self.assertNotEqual(child_thread_id, root_thread_id)
        self.assertEqual(child["thread"]["parent_thread_id"], root_thread_id)
        self.assertEqual(child["thread"]["root_thread_id"], root_thread_id)

        await self.harness.wait_for(
            lambda: len(specialist.events) >= 1,
            message="specialist did not receive the child-thread message",
        )
        self.assertEqual(specialist.events[-1]["thread_id"], child_thread_id)

        closed = await self.harness.send_notification(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            thread_id=root_thread_id,
            status="closed",
            message_text="Stop work.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

        await self.harness.wait_for(
            lambda: len(specialist.stops) >= 1,
            message="specialist did not receive stop from child cascade",
        )
        self.assertEqual(specialist.stops[-1]["thread_id"], child_thread_id)

        child_state = await self.harness.get_thread(child_thread_id)
        self.assertEqual(child_state["thread"]["status"], "closed")
        self.assertEqual(child_state["thread"]["parent_thread_id"], root_thread_id)

    async def test_inactivity_wakeup_and_delivery_retry_after_agent_restart(self) -> None:
        secretary = await self.harness.add_agent("secretary")
        orchestra = await self.harness.add_agent("orchestra")

        initial = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Ping and wait.",
        )
        inactivity_thread_id = str(initial["thread"]["thread_id"])
        await self.harness.wait_for(
            lambda: len(orchestra.events) >= 1,
            message="orchestra did not receive initial message before inactivity test",
        )

        await self.harness.wait_for(
            lambda: any(event.get("event_kind") == "inactive" for event in secretary.events),
            timeout=6.0,
            message="secretary did not receive inactivity wakeup",
        )
        inactivity_event = next(event for event in secretary.events if event.get("event_kind") == "inactive")
        self.assertEqual(inactivity_event["thread_id"], inactivity_thread_id)

        await orchestra.stop()
        retry_payload = await self.harness.send_message(
            from_agent_slug=secretary.slug,
            to_agent_slug=orchestra.slug,
            message_text="Deliver this after restart.",
        )
        retry_thread_id = str(retry_payload["thread"]["thread_id"])
        self.assertEqual(retry_thread_id, inactivity_thread_id)

        async def _delivery_attempt_started() -> bool:
            thread = await self.harness.service.store.get_thread(retry_thread_id)
            if not thread:
                return False
            events = await self.harness.service.store.list_thread_events(thread_id=retry_thread_id, limit=20)
            return bool(events) and int(events[-1]["delivery_attempt_count"]) >= 1

        await self.harness.wait_for(
            _delivery_attempt_started,
            timeout=4.0,
            message="pending event was not retried while orchestra was offline",
        )

        event_count_before_restart = len(orchestra.events)
        await orchestra.start()
        await self.harness.register_agent(orchestra)

        await self.harness.wait_for(
            lambda: len(orchestra.events) > event_count_before_restart,
            timeout=6.0,
            message="retried event was not delivered after orchestra restart",
        )
        self.assertEqual(orchestra.events[-1]["message_text"], "Deliver this after restart.")

        closed = await self.harness.close_thread(
            owner_agent=secretary,
            peer_agent=orchestra,
            thread_id=retry_thread_id,
            message_text="Closing inactivity-retry test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")


if __name__ == "__main__":
    unittest.main()
