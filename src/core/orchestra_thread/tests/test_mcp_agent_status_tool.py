from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from core.orchestra_thread.mcp.server import OrchestraThreadsMCPServer


def _structured(result: dict[str, object]) -> dict[str, object]:
    payload = result["structuredContent"]
    assert isinstance(payload, dict)
    return payload


class MCPAgentStatusToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_status_returns_busy_snapshot(self) -> None:
        client = AsyncMock()
        client.get_agent_status.return_value = {
            "success": True,
            "agent_slug": "secretary",
            "online": True,
            "busy": True,
            "status": "in_progress",
            "current_thread_id": "thread-123",
        }
        server = OrchestraThreadsMCPServer(agent_slug="whiner", client=client)

        result = await server.handle_tools_call(
            name="agent_status",
            arguments={"agent_slug": "secretary"},
        )

        payload = _structured(result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "agent_status")
        self.assertEqual(payload["agent_slug"], "secretary")
        self.assertTrue(payload["online"])
        self.assertTrue(payload["busy"])
        self.assertEqual(payload["status"], "in_progress")
        self.assertEqual(payload["current_thread_id"], "thread-123")
        client.get_agent_status.assert_awaited_once_with(agent_slug="secretary")

        await server.close()
