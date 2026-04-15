from __future__ import annotations

import asyncio
import subprocess
import unittest
from importlib import import_module
from uuid import uuid4

_support = import_module("core.orchestra_memory.tests._memory_secretary_e2e_support")
SecretaryMemorySupport = _support.SecretaryMemorySupport
SecretaryRpcSupport = _support.SecretaryRpcSupport
SecretaryServerSupport = _support.SecretaryServerSupport


class SecretaryMemoryE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._processes: list[subprocess.Popen[str]] = []

    async def asyncTearDown(self) -> None:
        while self._processes:
            process = self._processes.pop()
            await SecretaryServerSupport.cleanup_server(process)

    async def test_secretary_mcp_server_initializes(self) -> None:
        process = await SecretaryServerSupport.start_initialized_server(
            "secretary",
            self._processes,
        )
        response = await SecretaryRpcSupport.send_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": SecretaryRpcSupport.response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )

        self.assertEqual(response["result"]["serverInfo"]["name"], "orchestra-memory-mcp")
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")

    async def test_secretary_can_remember_and_search(self) -> None:
        process = await SecretaryServerSupport.start_initialized_server(
            "secretary",
            self._processes,
        )
        token = f"secretary-memory-{uuid4().hex}"

        remember_result = await SecretaryMemorySupport.remember_memory(
            process,
            token,
            "knowledge",
        )
        self.assertTrue(SecretaryRpcSupport.structured_content(remember_result)["ok"])

        items = await SecretaryMemorySupport.search_memory_items(
            process,
            token,
            "knowledge",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], token)
        self.assertEqual(items[0]["agent_slug"], "secretary")

        http_status, http_body = await SecretaryMemorySupport.search_memory_http(token)
        self.assertEqual(http_status, 200)
        self.assertEqual(http_body["items"][0]["text"], token)

    async def test_secretary_discovery_tools_work(self) -> None:
        process = await SecretaryServerSupport.start_initialized_server(
            "secretary",
            self._processes,
        )
        token = f"secretary-discovery-{uuid4().hex}"

        await SecretaryMemorySupport.remember_memory(process, token, "profile")
        rooms, categories = await SecretaryMemorySupport.check_memory_discovery(
            process,
        )
        self.assertIn("profile", rooms)
        self.assertIn("fact", categories)

        rooms_status, rooms_body = await SecretaryMemorySupport.post_memory_json(
            "/memory/discovery/rooms", {"agent_slug": "secretary"}
        )
        categories_status, categories_body = await SecretaryMemorySupport.post_memory_json(
            "/memory/discovery/categories",
            {"agent_slug": "secretary"},
        )
        self.assertEqual(rooms_status, 200)
        self.assertEqual(categories_status, 200)
        self.assertIn("profile", rooms_body["rooms"])
        self.assertIn("fact", categories_body["categories"])

    async def test_secretary_slug_scoping_isolation(self) -> None:
        secretary_process = SecretaryServerSupport.start_mcp_server("secretary")
        orchestra_process = SecretaryServerSupport.start_mcp_server("orchestra")
        self._processes.extend([secretary_process, orchestra_process])

        await asyncio.gather(
            SecretaryRpcSupport.initialize_server(secretary_process),
            SecretaryRpcSupport.initialize_server(orchestra_process),
        )

        secretary_token = f"secretary-isolation-{uuid4().hex}"
        orchestra_token = f"orchestra-isolation-{uuid4().hex}"

        await SecretaryMemorySupport.remember_memory(
            secretary_process,
            secretary_token,
            "knowledge",
        )
        await SecretaryMemorySupport.remember_memory(
            orchestra_process,
            orchestra_token,
            "knowledge",
        )

        secretary_results = await SecretaryMemorySupport.search_memory_items(
            secretary_process, secretary_token, "knowledge"
        )
        orchestra_results = await SecretaryMemorySupport.search_memory_items(
            orchestra_process, orchestra_token, "knowledge"
        )

        self.assertEqual(len(secretary_results), 1)
        self.assertEqual(secretary_results[0]["text"], secretary_token)
        self.assertEqual(secretary_results[0]["agent_slug"], "secretary")
        self.assertEqual(len(orchestra_results), 1)
        self.assertEqual(orchestra_results[0]["text"], orchestra_token)
        self.assertEqual(orchestra_results[0]["agent_slug"], "orchestra")

    async def test_secretary_memory_persists_across_restart(self) -> None:
        process = await SecretaryServerSupport.start_initialized_server(
            "secretary",
            self._processes,
        )
        token = f"secretary-persist-{uuid4().hex}"

        await SecretaryMemorySupport.remember_memory(process, token, "knowledge")
        initial_status, initial_body = await SecretaryMemorySupport.search_memory_http(
            token,
        )
        self.assertEqual(initial_status, 200)
        self.assertEqual(initial_body["items"][0]["text"], token)

        restarted_process = await SecretaryServerSupport.restart_server(
            process,
            "secretary",
            self._processes,
        )
        search_result = await SecretaryMemorySupport.search_memory_result(
            restarted_process,
            token,
            "knowledge",
        )
        self.assertEqual(search_result["count"], 1)
        self.assertEqual(search_result["items"][0]["text"], token)
        self.assertEqual(search_result["items"][0]["agent_slug"], "secretary")
