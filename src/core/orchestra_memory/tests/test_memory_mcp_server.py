# noqa: WPS214
from __future__ import annotations

import unittest
from typing import Any

from core.orchestra_memory.mcp.server import (
    OrchestraMemoryMCPServer,
    orchestra_memory_tool_definitions,
)


class _FakeMemoryClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "operation": "remember",
                "agent_slug": agent_slug,
                "room": room,
                "category": category,
                "text": text,
            }
        )
        return {
            "memory_id": "mem-1",
            "agent_slug": agent_slug,
            "room": room,
            "category": category,
            "text": text,
        }

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "operation": "search",
                "agent_slug": agent_slug,
                "query": query,
                "room": room,
                "category": category,
                "limit": limit,
            }
        )
        return [{"memory_id": "mem-1", "text": "hello", "agent_slug": agent_slug}]

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool:
        self.calls.append(
            {
                "operation": "delete",
                "agent_slug": agent_slug,
                "memory_id": memory_id,
            }
        )
        return True

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int:
        self.calls.append(
            {
                "operation": "clear",
                "agent_slug": agent_slug,
                "room": room,
                "category": category,
            }
        )
        return 2

    async def list_rooms(self, *, agent_slug: str) -> list[str]:
        self.calls.append(
            {
                "operation": "list_rooms",
                "agent_slug": agent_slug,
            }
        )
        return []

    async def list_categories(self, *, agent_slug: str) -> list[str]:
        self.calls.append(
            {
                "operation": "list_categories",
                "agent_slug": agent_slug,
            }
        )
        return []

    async def close(self) -> None:
        self.closed = True


class OrchestraMemoryMCPServerTests(unittest.IsolatedAsyncioTestCase):
    def test_tool_definitions_export_match_tools(self) -> None:
        tool_names = {tool["name"] for tool in orchestra_memory_tool_definitions()}

        self.assertEqual(
            tool_names,
            {
                "memory_remember",
                "memory_search",
                "memory_delete",
                "memory_clear",
                "memory_list_rooms",
                "memory_list_categories",
            },
        )

    async def test_discovery_tools_in_tool_list(self) -> None:
        client = _FakeMemoryClient()
        server = OrchestraMemoryMCPServer(agent_slug="secretary", client=client)

        tools = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/list",
                "params": {},
            }
        )
        assert tools is not None
        names = {item["name"] for item in tools["result"]["tools"]}
        self.assertTrue({"memory_list_rooms", "memory_list_categories"}.issubset(names))
        await server.close()
        self.assertTrue(client.closed)

    async def test_initialize_and_tools_list(self) -> None:
        client = _FakeMemoryClient()
        server = OrchestraMemoryMCPServer(agent_slug="secretary", client=client)

        initialize = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "initialize",
                "params": {},
            }
        )
        assert initialize is not None
        self.assertEqual(initialize["result"]["serverInfo"]["name"], "orchestra-memory-mcp")

        tools = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tools/list",
                "params": {},
            }
        )
        assert tools is not None
        names = {item["name"] for item in tools["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "memory_remember",
                "memory_search",
                "memory_delete",
                "memory_clear",
                "memory_list_rooms",
                "memory_list_categories",
            },
        )
        await server.close()
        self.assertTrue(client.closed)

    async def test_scope_enforcement_rejects_slug_override(self) -> None:
        server = OrchestraMemoryMCPServer(agent_slug="orchestra", client=_FakeMemoryClient())
        response = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "x", "agent_slug": "override"},
                },
            }
        )
        assert response is not None
        self.assertEqual(response["error"]["code"], -32000)
        self.assertIn("agent_slug override is not allowed", response["error"]["message"])
        await server.close()

    async def test_backend_uses_server_agent_slug(self) -> None:
        client = _FakeMemoryClient()
        server = OrchestraMemoryMCPServer(agent_slug="secretary", client=client)

        await self._call_tool(
            server,
            tool_name="memory_remember",
            arguments={
                "text": "remember this",
                "room": "knowledge",
                "category": "fact",
            },
        )
        await self._call_tool(
            server,
            tool_name="memory_search",
            arguments={"query": "remember", "room": "knowledge", "limit": 3},
        )
        await self._call_tool(
            server,
            tool_name="memory_delete",
            arguments={"memory_id": "mem-1"},
        )
        await self._call_tool(
            server,
            tool_name="memory_clear",
            arguments={"category": "fact"},
        )

        self._assert_client_calls(client.calls)
        await server.close()

    async def test_memory_list_rooms_calls_client(self) -> None:
        client = _FakeMemoryClient()
        server = OrchestraMemoryMCPServer(agent_slug="secretary", client=client)

        await self._call_tool(
            server,
            tool_name="memory_list_rooms",
            arguments={},
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "operation": "list_rooms",
                    "agent_slug": "secretary",
                },
            ],
        )
        await server.close()

    async def test_memory_list_categories_calls_client(self) -> None:
        client = _FakeMemoryClient()
        server = OrchestraMemoryMCPServer(agent_slug="secretary", client=client)

        await self._call_tool(
            server,
            tool_name="memory_list_categories",
            arguments={},
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "operation": "list_categories",
                    "agent_slug": "secretary",
                },
            ],
        )
        await server.close()

    async def _call_tool(
        self,
        server: OrchestraMemoryMCPServer,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        response = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": tool_name,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        )
        assert response is not None
        self.assertIn("result", response)

    def _assert_client_calls(self, calls: list[dict[str, Any]]) -> None:
        self.assertEqual(
            [call["operation"] for call in calls],
            ["remember", "search", "delete", "clear"],
        )
        self.assertEqual(
            [call["agent_slug"] for call in calls],
            ["secretary", "secretary", "secretary", "secretary"],
        )
        self.assertEqual(calls[0]["room"], "knowledge")
        self.assertEqual(calls[1]["limit"], 3)
        self.assertEqual(calls[2]["memory_id"], "mem-1")
        self.assertEqual(calls[3]["category"], "fact")
