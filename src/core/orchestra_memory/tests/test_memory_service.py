from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from aiohttp.test_utils import AioHTTPTestCase

from core.orchestra_agents import runtime as agent_runtime
from core.orchestra_memory import config as memory_config
from core.orchestra_memory import service_runtime as memory_runtime
from core.orchestra_memory.tests.fakes import fake_import_module


class MemoryServiceHttpTests(AioHTTPTestCase):
    async def get_application(self) -> Any:
        self._tempdir = tempfile.TemporaryDirectory()
        config = memory_config.OrchestraMemoryConfig(
            host="127.0.0.1",
            port=0,
            storage_path=Path(self._tempdir.name) / "palace",
            allowed_rooms=("profile", "knowledge", "task"),
            allowed_categories=("fact", "preference", "instruction"),
        )
        self._service = memory_runtime.OrchestraMemoryService(config)
        self._patcher = patch(
            "core.orchestra_memory.store.import_module",
            side_effect=fake_import_module,
        )
        self._patcher.start()
        await self._service.start()
        return memory_runtime.build_app(self._service)

    async def tearDownAsync(self) -> None:
        await self._service.stop()
        self._patcher.stop()
        self._tempdir.cleanup()
        await super().tearDownAsync()

    async def test_remember_and_search_is_scoped_by_slug(self) -> None:
        await self.client.post(
            "/memory/remember",
            json={
                "agent_slug": "agent-a",
                "room": "profile",
                "category": "fact",
                "text": "alpha secret",
            },
        )
        await self.client.post(
            "/memory/remember",
            json={
                "agent_slug": "agent-b",
                "room": "profile",
                "category": "fact",
                "text": "beta secret",
            },
        )
        response = await self.client.post(
            "/memory/search",
            json={"agent_slug": "agent-a", "query": "secret", "limit": 10},
        )
        body = await response.json()
        self.assertEqual(response.status, 200)
        items = body["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["agent_slug"], "agent-a")
        self.assertEqual(items[0]["text"], "alpha secret")

    async def test_clear_and_delete_only_affect_explicit_memory_operations(self) -> None:
        memory_id = await self._remember_memory(text="remember me")
        clear_body = await self._post_json("/memory/clear", {"agent_slug": "agent-b"})
        self.assertEqual(clear_body["deleted_count"], 0)
        delete_body = await self._post_json(
            "/memory/delete",
            {"agent_slug": "agent-a", "memory_id": memory_id},
        )
        self.assertTrue(delete_body["deleted"])
        verify_body = await self._post_json(
            "/memory/search",
            {"agent_slug": "agent-a", "query": "remember me", "limit": 10},
        )
        self.assertEqual(verify_body["items"], [])

    async def _remember_memory(self, *, text: str) -> str:
        remember_body = await self._post_json(
            "/memory/remember",
            {
                "agent_slug": "agent-a",
                "room": "task",
                "category": "instruction",
                "text": text,
            },
        )
        memory = remember_body.get("memory")
        if not isinstance(memory, dict):
            raise AssertionError("memory payload is missing")
        return str(memory["memory_id"])

    async def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        response = await self.client.post(path, json=payload)
        self.assertEqual(response.status, 200)
        body = await response.json()
        return cast(dict[str, object], body)


class MemoryStorePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistence_after_recreating_store(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config = memory_config.OrchestraMemoryConfig(
                host="127.0.0.1",
                port=0,
                storage_path=Path(tempdir) / "palace",
                allowed_rooms=("profile", "knowledge", "task"),
                allowed_categories=("fact", "preference", "instruction"),
            )
            with patch(
                "core.orchestra_memory.store.import_module",
                side_effect=fake_import_module,
            ):
                await self._assert_persistence(config)

    async def _assert_persistence(self, config: memory_config.OrchestraMemoryConfig) -> None:
        await self._remember_and_stop(config)
        await self._assert_reloaded_memory(config)

    async def _remember_and_stop(self, config: memory_config.OrchestraMemoryConfig) -> None:
        service = memory_runtime.OrchestraMemoryService(config)
        await service.start()
        await service.remember(
            agent_slug="agent-persist",
            room="knowledge",
            category="fact",
            text="stable memory",
        )
        await service.stop()

    async def _assert_reloaded_memory(self, config: memory_config.OrchestraMemoryConfig) -> None:
        service = memory_runtime.OrchestraMemoryService(config)
        await service.start()
        results = await service.search(
            agent_slug="agent-persist",
            query="stable",
            room=None,
            category=None,
            limit=10,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "stable memory")
        await service.stop()


class _DummyAgentBackend(agent_runtime.BaseAgentBackend):
    async def handle_events(
        self,
        delivery: agent_runtime.EventDelivery,
    ) -> agent_runtime.EventDeliveryResult:
        self.remember_delivery(delivery)
        return agent_runtime.EventDeliveryResult(accepted=True, accepted_events=0)


class MemoryClearContextIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self._config = memory_config.OrchestraMemoryConfig(
            host="127.0.0.1",
            port=0,
            storage_path=Path(self._tempdir.name) / "palace",
            allowed_rooms=("profile", "knowledge", "task"),
            allowed_categories=("fact", "preference", "instruction"),
        )
        self._patcher = patch(
            "core.orchestra_memory.store.import_module",
            side_effect=fake_import_module,
        )
        self._patcher.start()
        self._service = memory_runtime.OrchestraMemoryService(self._config)
        await self._service.start()
        self._backend = _DummyAgentBackend(
            agent_slug="agent-a",
            backend_type="dummy",
            working_dir="/workspace",
        )
        self._agent_app = agent_runtime.StandardAgentApplication(
            backend=self._backend,
            host="127.0.0.1",
            port=0,
        )
        await self._agent_app.start()

    async def asyncTearDown(self) -> None:
        await self._agent_app.stop()
        await self._service.stop()
        self._patcher.stop()
        self._tempdir.cleanup()

    async def test_agent_clear_context_does_not_remove_memory(self) -> None:
        await self._service.remember(
            agent_slug="agent-a",
            room="knowledge",
            category="fact",
            text="persistent memory",
        )
        await self._backend.clear_context(_clear_context_request())

        results = await self._service.search(
            agent_slug="agent-a",
            query="persistent",
            room=None,
            category=None,
            limit=10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "persistent memory")


def _clear_context_request() -> Any:
    from core.orchestra_agents.runtime.contracts import ClearContextRequest

    return ClearContextRequest(requested_by="test")
