from __future__ import annotations

import asyncio
from collections.abc import Mapping

from core.orchestra_thread.tests.fixtures import BaseE2ETestCase, add_pair
from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent


def _agent_online_map(agents_payload: dict[str, object]) -> dict[str, bool]:
    listed_agents = agents_payload["agents"]
    assert isinstance(listed_agents, list)
    return {str(item["agent_slug"]): bool(item["online"]) for item in listed_agents}


def _agent_last_seen(agents_payload: dict[str, object], agent_slug: str) -> object:
    listed_agents = agents_payload["agents"]
    assert isinstance(listed_agents, list)
    return next(item for item in listed_agents if item["agent_slug"] == agent_slug)["last_seen_at"]


class AgentLifecycleE2ETests(BaseE2ETestCase):
    async def test_agents_report_online_after_heartbeat(self) -> None:
        agents = await add_pair(self.harness)
        agents_payload = await self.harness.list_agents()
        online_map = _agent_online_map(agents_payload)
        self.assertTrue(online_map.get(agents["secretary"].slug))
        self.assertTrue(online_map.get(agents["orchestra"].slug))

        before = _agent_last_seen(agents_payload, agents["secretary"].slug)
        await asyncio.sleep(0.02)
        heartbeat_payload = await self.harness.heartbeat(agents["secretary"].slug)
        self.assertNotEqual(before, heartbeat_payload["agent"]["last_seen_at"])
        self.assertTrue(heartbeat_payload["agent"]["online"])

    async def test_agent_status_endpoint_reports_busy_thread(self) -> None:
        agents = await add_pair(self.harness)
        await self.harness.add_agent("specialist")
        await _run_busy_status_flow(self, self.harness, agents)


async def _assert_idle_status(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    agent_slug: str,
) -> None:
    status_payload = await harness.get_agent_status(agent_slug)
    case.assertEqual(status_payload["status"], "idle")
    case.assertIsNone(status_payload["current_thread_id"])


async def _run_busy_status_flow(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    agents: Mapping[str, FakeAgent],
) -> None:
    await _assert_idle_status(case, harness, agents["orchestra"].slug)
    thread_id = await _open_busy_thread(harness, agents)
    await _assert_busy_status(case, harness, agents["orchestra"].slug, thread_id)
    await _close_busy_thread(harness, agents, thread_id)
    await _assert_idle_status(case, harness, agents["orchestra"].slug)


async def _open_busy_thread(harness: E2EHarness, agents: Mapping[str, FakeAgent]) -> str:
    root = await harness.send_message(
        {
            "from_agent_slug": agents["secretary"].slug,
            "to_agent_slug": agents["orchestra"].slug,
            "message_text": "Investigate this issue.",
        }
    )
    thread_id = str(root["thread"]["thread_id"])
    await harness.send_notification(
        {
            "from_agent_slug": agents["orchestra"].slug,
            "to_agent_slug": agents["secretary"].slug,
            "thread_id": thread_id,
            "status": "in_progress",
            "message_text": "Working on it.",
        }
    )
    return thread_id


async def _assert_busy_status(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    agent_slug: str,
    thread_id: str,
) -> None:
    busy_status = await harness.get_agent_status(agent_slug)
    case.assertEqual(busy_status["status"], "in_progress")
    case.assertTrue(busy_status["busy"])
    case.assertEqual(busy_status["current_thread_id"], thread_id)


async def _close_busy_thread(
    harness: E2EHarness,
    agents: Mapping[str, FakeAgent],
    thread_id: str,
) -> None:
    await harness.close_thread(
        owner_agent=agents["secretary"],
        peer_agent=agents["orchestra"],
        thread_id=thread_id,
        message_text="Closing busy-status test thread.",
    )
