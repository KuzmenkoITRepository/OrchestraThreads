from __future__ import annotations

import asyncio

from core.orchestra_thread.tests.fixtures import BaseE2ETestCase, add_pair


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
