"""Tests for the compact OrchestraThreads MCP server."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from core.orchestra_thread import active_context as active_context_module
from core.orchestra_thread.active_context import clear_active_context, write_active_context
from core.orchestra_thread.client import OrchestraThreadsClient
from core.orchestra_thread.mcp_server import OrchestraThreadsMCPServer
from core.orchestra_thread.tests.test_e2e_mvp import E2EHarness


def _structured(result: dict[str, Any]) -> dict[str, Any]:
    return dict(result["structuredContent"])


@asynccontextmanager
async def _server_ctx(
    harness: E2EHarness,
    agent_slug: str,
) -> AsyncIterator[OrchestraThreadsMCPServer]:
    assert harness.base_url is not None
    server = OrchestraThreadsMCPServer(
        agent_slug=agent_slug,
        client=OrchestraThreadsClient(base_url=harness.base_url),
    )
    try:
        yield server
    finally:
        await server.close()


async def _create_root_context(
    harness: E2EHarness,
    orchestra: Any,
) -> str:
    root = await harness.send_message(
        from_agent_slug="secretary",
        to_agent_slug="orchestra",
        message_text="Prepare a short update.",
    )
    thread_id = str(root["thread"]["thread_id"])
    await harness.wait_for(
        lambda: len(orchestra.events) >= 1,
        message="orchestra did not receive the initial root-thread message",
    )
    write_active_context(
        {
            "thread_id": thread_id,
            "root_thread_id": thread_id,
            "parent_thread_id": None,
            "source_agent_slug": "secretary",
            "target_agent_slug": "orchestra",
            "owner_agent_slug": "secretary",
        },
    )
    return thread_id


class MCPServerSetupMixin(unittest.IsolatedAsyncioTestCase):
    """Base setup/teardown for MCP server tests."""

    harness: E2EHarness
    secretary: Any
    orchestra: Any
    specialist: Any

    async def asyncSetUp(self) -> None:
        self.context_path = (
            Path(tempfile.mkdtemp(prefix="orchestra_threads_mcp_ctx_")) / "active_context.json"
        )
        self.original_context_path = active_context_module.ACTIVE_CONTEXT_PATH
        active_context_module.ACTIVE_CONTEXT_PATH = self.context_path
        clear_active_context()

        self.harness = E2EHarness()
        await self.harness.start()
        self.secretary = await self.harness.add_agent("secretary")
        self.orchestra = await self.harness.add_agent("orchestra")
        self.specialist = await self.harness.add_agent("specialist")

    async def asyncTearDown(self) -> None:
        clear_active_context()
        active_context_module.ACTIVE_CONTEXT_PATH = self.original_context_path
        await self.harness.stop()


class MCPSendToolTests(MCPServerSetupMixin):
    """Tests for thread_send and thread_current MCP tools."""

    async def test_send_creates_root(self) -> None:
        async with _server_ctx(self.harness, "secretary") as server:
            result = await server.handle_tools_call(
                name="thread_send",
                arguments={
                    "target_agent_slug": "orchestra",
                    "message": "Prepare a short update.",
                },
            )
        payload = _structured(result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "thread_send")
        self.assertEqual(payload["route"], "created_root")
        self.assertEqual(payload["peer_agent_slug"], "orchestra")
        self.assertIsNotNone(payload["thread_id"])

        await self._close_root(str(payload["thread_id"]))

    async def test_current_reply_and_child(self) -> None:
        thread_id = await _create_root_context(self.harness, self.orchestra)
        async with _server_ctx(self.harness, "orchestra") as server:
            await self._verify_current(server, thread_id)
            await self._verify_reply(server, thread_id)
            await self._verify_child(server, thread_id)
        await self._close_root(thread_id)

    async def _verify_current(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        current = _structured(
            await server.handle_tools_call(name="thread_current", arguments={}),
        )
        self.assertTrue(current["active"])
        self.assertEqual(current["thread_id"], thread_id)
        self.assertEqual(current["peer_agent_slug"], "secretary")
        self.assertIn("thread_send", current["allowed_actions"])

    async def _verify_reply(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        reply = _structured(
            await server.handle_tools_call(
                name="thread_send",
                arguments={"message": "Done. Here is the update."},
            ),
        )
        self.assertEqual(reply["route"], "reply_current")
        self.assertEqual(reply["thread_id"], thread_id)

    async def _verify_child(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        child = _structured(
            await server.handle_tools_call(
                name="thread_send",
                arguments={
                    "target_agent_slug": "specialist",
                    "message": "Check one detail.",
                },
            ),
        )
        self.assertEqual(child["route"], "created_child")
        self.assertNotEqual(child["thread_id"], thread_id)

    async def _close_root(self, thread_id: str) -> None:
        closed = await self.harness.close_thread(
            owner_agent=self.secretary,
            peer_agent=self.orchestra,
            thread_id=thread_id,
            message_text="Closing MCP test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")


class MCPStatusAndProtocolTests(MCPServerSetupMixin):
    """Tests for status, expand, guide, and protocol surface."""

    async def test_status_and_expand(self) -> None:
        thread_id = await _create_root_context(self.harness, self.orchestra)
        async with _server_ctx(self.harness, "orchestra") as server:
            await self._verify_status(server, thread_id)
            await self._verify_expand(server, thread_id)
        await self._close_root(thread_id)

    async def test_guide_returns_workflow(self) -> None:
        async with _server_ctx(self.harness, "secretary") as server:
            guide = _structured(
                await server.handle_tools_call(
                    name="thread_guide",
                    arguments={"section": "mcp", "view": "full"},
                ),
            )
        self.assertTrue(guide["ok"])
        self.assertEqual(guide["operation"], "thread_guide")
        self.assertEqual(guide["section"], "mcp")
        self.assertIn("recommended_mcp_tool_flow", guide)

    async def test_protocol_surface(self) -> None:
        async with _server_ctx(self.harness, "secretary") as server:
            init_resp = await server.handle_request(
                _init_request(),
            )
            resources = await server.handle_request(
                {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
            )
            templates = await server.handle_request(
                {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}},
            )
        self.assertEqual(init_resp["result"]["capabilities"], {"tools": {}, "resources": {}})
        self.assertEqual(resources["result"], {"resources": []})
        self.assertEqual(templates["result"], {"resourceTemplates": []})

    async def _verify_status(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        status = _structured(
            await server.handle_tools_call(
                name="thread_status",
                arguments={"status": "review", "message": "Ready for handoff."},
            ),
        )
        self.assertTrue(status["ok"])
        self.assertEqual(status["thread_id"], thread_id)
        self.assertEqual(status["published_status"], "review")
        await self.harness.wait_for(
            lambda: any(ev.get("notification_status") == "review" for ev in self.secretary.events),
            message="secretary did not receive review notification",
        )

    async def _verify_expand(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        latest = _structured(
            await server.handle_tools_call(
                name="thread_expand",
                arguments={"view": "latest"},
            ),
        )
        self.assertEqual(latest["thread"]["thread_id"], thread_id)
        related = _structured(
            await server.handle_tools_call(
                name="thread_expand",
                arguments={"view": "related"},
            ),
        )
        self.assertIn("related", related)

    async def _close_root(self, thread_id: str) -> None:
        closed = await self.harness.close_thread(
            owner_agent=self.secretary,
            peer_agent=self.orchestra,
            thread_id=thread_id,
            message_text="Closing MCP test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")


def _init_request() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }


if __name__ == "__main__":
    unittest.main()
