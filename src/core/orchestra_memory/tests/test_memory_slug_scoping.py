from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.orchestra_memory import config as memory_config
from core.orchestra_memory import service_runtime as memory_runtime
from core.orchestra_memory.tests.fakes import fake_import_module


class AgentSlugScopingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self._patcher = patch(
            "core.orchestra_memory.store.import_module",
            side_effect=fake_import_module,
        )
        self._patcher.start()

        config = memory_config.OrchestraMemoryConfig(
            host="127.0.0.1",
            port=0,
            storage_path=Path(self._tempdir.name) / "palace",
        )
        self._service_a = memory_runtime.OrchestraMemoryService(config)
        self._service_b = memory_runtime.OrchestraMemoryService(config)
        await self._service_a.start()
        await self._service_b.start()

    async def asyncTearDown(self) -> None:
        await self._service_b.stop()
        await self._service_a.stop()
        self._patcher.stop()
        self._tempdir.cleanup()

    async def test_delete_only_affects_calling_agent(self) -> None:
        memory_id = await self._remember(
            self._service_a,
            agent_slug="agent_a",
            room="profile",
            category="fact",
            text="agent a secret",
        )

        deleted = await self._service_b.delete(agent_slug="agent_b", memory_id=memory_id)

        self.assertFalse(deleted)
        self.assertEqual(
            self._normalize_search_results(
                await self._search(self._service_a, agent_slug="agent_a", query="agent a secret")
            ),
            [
                {
                    "memory_id": memory_id,
                    "agent_slug": "agent_a",
                    "room": "profile",
                    "category": "fact",
                    "text": "agent a secret",
                }
            ],
        )

    async def test_clear_only_affects_calling_agent(self) -> None:
        agent_a_id = await self._remember(
            self._service_a,
            agent_slug="agent_a",
            room="tasks",
            category="instruction",
            text="agent a memory",
        )
        agent_b_id = await self._remember(
            self._service_b,
            agent_slug="agent_b",
            room="tasks",
            category="instruction",
            text="agent b memory",
        )

        deleted_count = await self._service_a.clear(
            agent_slug="agent_a",
            room=None,
            category=None,
        )

        self.assertEqual(deleted_count, 1)
        self.assertEqual(
            self._normalize_search_results(
                await self._search(self._service_a, agent_slug="agent_a", query="agent a memory")
            ),
            [],
        )
        self.assertEqual(
            self._normalize_search_results(
                await self._search(self._service_b, agent_slug="agent_b", query="agent b memory")
            ),
            [
                {
                    "memory_id": agent_b_id,
                    "agent_slug": "agent_b",
                    "room": "tasks",
                    "category": "instruction",
                    "text": "agent b memory",
                }
            ],
        )
        self.assertNotEqual(agent_a_id, agent_b_id)

    async def test_discovery_returns_only_calling_agent_data(self) -> None:
        await self._remember(
            self._service_a,
            agent_slug="agent_a",
            room="profile",
            category="fact",
            text="agent a profile fact",
        )
        await self._remember(
            self._service_a,
            agent_slug="agent_a",
            room="notes",
            category="reminder",
            text="agent a note",
        )
        await self._remember(
            self._service_b,
            agent_slug="agent_b",
            room="archive",
            category="idea",
            text="agent b archive idea",
        )
        await self._remember(
            self._service_b,
            agent_slug="agent_b",
            room="logs",
            category="warning",
            text="agent b log warning",
        )

        self.assertEqual(
            await self._service_a.list_rooms(agent_slug="agent_a"),
            ["notes", "profile"],
        )
        self.assertEqual(
            await self._service_a.list_categories(agent_slug="agent_a"),
            ["fact", "reminder"],
        )
        self.assertEqual(
            await self._service_b.list_rooms(agent_slug="agent_b"),
            ["archive", "logs"],
        )
        self.assertEqual(
            await self._service_b.list_categories(agent_slug="agent_b"),
            ["idea", "warning"],
        )

    def _normalize_search_results(self, items: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in items:
            normalized.append(
                {
                    "memory_id": item["memory_id"],
                    "agent_slug": item["agent_slug"],
                    "room": item["room"],
                    "category": item["category"],
                    "text": item["text"],
                }
            )
        return normalized

    async def _remember(
        self,
        service: memory_runtime.OrchestraMemoryService,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> str:
        memory = await service.remember(
            agent_slug=agent_slug,
            room=room,
            category=category,
            text=text,
        )
        return memory["memory_id"]

    async def _search(
        self,
        service: memory_runtime.OrchestraMemoryService,
        *,
        agent_slug: str,
        query: str,
    ) -> list[dict[str, str]]:
        return await service.search(
            agent_slug=agent_slug,
            query=query,
            room=None,
            category=None,
            limit=10,
        )
