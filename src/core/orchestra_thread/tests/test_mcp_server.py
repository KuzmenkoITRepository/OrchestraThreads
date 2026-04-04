"""Tests for the compact OrchestraThreads MCP server."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.orchestra_thread import active_context as active_context_module
from core.orchestra_thread.active_context import clear_active_context, write_active_context
from core.orchestra_thread.client import OrchestraThreadsClient
from core.orchestra_thread.mcp_server import OrchestraThreadsMCPServer
from core.orchestra_thread.tests.test_e2e_mvp import E2EHarness


def _structured(result: dict) -> dict:
    return result["structuredContent"]


class OrchestraThreadsMCPServerTestCase(unittest.IsolatedAsyncioTestCase):
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

    def _server(self, agent_slug: str) -> OrchestraThreadsMCPServer:
        assert self.harness.base_url is not None
        return OrchestraThreadsMCPServer(
            agent_slug=agent_slug,
            client=OrchestraThreadsClient(base_url=self.harness.base_url),
        )

    async def test_thread_send_creates_root_without_active_context(self) -> None:
        server = self._server("secretary")
        try:
            result = await server.handle_tools_call(
                name="thread_send",
                arguments={
                    "target_agent_slug": "orchestra",
                    "message": "Prepare a short update.",
                },
            )
        finally:
            await server.close()
        payload = _structured(result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "thread_send")
        self.assertEqual(payload["route"], "created_root")
        self.assertEqual(payload["peer_agent_slug"], "orchestra")
        self.assertIsNotNone(payload["thread_id"])

        closed = await self.harness.close_thread(
            owner_agent=self.secretary,
            peer_agent=self.orchestra,
            thread_id=str(payload["thread_id"]),
            message_text="Closing MCP root-send test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

    async def test_thread_current_auto_reply_and_child_use_active_context(self) -> None:
        root = await self.harness.send_message(
            from_agent_slug="secretary",
            to_agent_slug="orchestra",
            message_text="Prepare a short update.",
        )
        root_thread_id = str(root["thread"]["thread_id"])
        await self.harness.wait_for(
            lambda: len(self.orchestra.events) >= 1,
            message="orchestra did not receive the initial root-thread message",
        )
        write_active_context(
            {
                "thread_id": root_thread_id,
                "root_thread_id": root_thread_id,
                "parent_thread_id": None,
                "source_agent_slug": "secretary",
                "target_agent_slug": "orchestra",
                "owner_agent_slug": "secretary",
            }
        )

        server = self._server("orchestra")
        try:
            current = _structured(
                await server.handle_tools_call(name="thread_current", arguments={})
            )
            self.assertTrue(current["active"])
            self.assertEqual(current["thread_id"], root_thread_id)
            self.assertEqual(current["peer_agent_slug"], "secretary")
            self.assertIn("thread_send", current["allowed_actions"])

            reply = _structured(
                await server.handle_tools_call(
                    name="thread_send",
                    arguments={"message": "Done. Here is the update."},
                )
            )
            self.assertEqual(reply["route"], "reply_current")
            self.assertEqual(reply["thread_id"], root_thread_id)
            self.assertEqual(reply["peer_agent_slug"], "secretary")

            child = _structured(
                await server.handle_tools_call(
                    name="thread_send",
                    arguments={
                        "target_agent_slug": "specialist",
                        "message": "Check one detail.",
                    },
                )
            )
            self.assertEqual(child["route"], "created_child")
            self.assertNotEqual(child["thread_id"], root_thread_id)
            self.assertEqual(child["parent_thread_id"], root_thread_id)
            self.assertEqual(child["peer_agent_slug"], "specialist")
        finally:
            await server.close()

        closed = await self.harness.close_thread(
            owner_agent=self.secretary,
            peer_agent=self.orchestra,
            thread_id=root_thread_id,
            message_text="Closing MCP reply/current test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

    async def test_thread_status_and_expand_work_without_explicit_thread_id(self) -> None:
        root = await self.harness.send_message(
            from_agent_slug="secretary",
            to_agent_slug="orchestra",
            message_text="Prepare a short update.",
        )
        thread_id = str(root["thread"]["thread_id"])
        await self.harness.wait_for(
            lambda: len(self.orchestra.events) >= 1,
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
            }
        )

        server = self._server("orchestra")
        try:
            status = _structured(
                await server.handle_tools_call(
                    name="thread_status",
                    arguments={
                        "status": "review",
                        "message": "Ready for handoff.",
                    },
                )
            )
            self.assertTrue(status["ok"])
            self.assertEqual(status["thread_id"], thread_id)
            self.assertEqual(status["published_status"], "review")
            self.assertTrue(status["delivered"])

            await self.harness.wait_for(
                lambda: any(
                    event.get("notification_status") == "review" for event in self.secretary.events
                ),
                message="secretary did not receive review notification from MCP status tool",
            )

            latest = _structured(
                await server.handle_tools_call(
                    name="thread_expand",
                    arguments={"view": "latest"},
                )
            )
            self.assertEqual(latest["thread"]["thread_id"], thread_id)
            self.assertEqual(latest["latest_event"]["notification_status"], "review")

            related = _structured(
                await server.handle_tools_call(
                    name="thread_expand",
                    arguments={"view": "related"},
                )
            )
            self.assertIn("related", related)
            self.assertEqual(related["thread"]["thread_id"], thread_id)
        finally:
            await server.close()

        closed = await self.harness.close_thread(
            owner_agent=self.secretary,
            peer_agent=self.orchestra,
            thread_id=thread_id,
            message_text="Closing MCP status test thread.",
        )
        self.assertEqual(closed["thread"]["status"], "closed")

    async def test_thread_guide_returns_service_workflow(self) -> None:
        server = self._server("secretary")
        try:
            guide = _structured(
                await server.handle_tools_call(
                    name="thread_guide",
                    arguments={"section": "mcp", "view": "full"},
                )
            )
        finally:
            await server.close()

        self.assertTrue(guide["ok"])
        self.assertEqual(guide["operation"], "thread_guide")
        self.assertEqual(guide["section"], "mcp")
        self.assertEqual(guide["view"], "full")
        self.assertIn("recommended_mcp_tool_flow", guide)
        self.assertIn("mcp_tools", guide)
        self.assertTrue(any("thread_guide" in item for item in guide["mcp_tools"]))

    async def test_protocol_surface_exposes_empty_resource_list_endpoints(self) -> None:
        server = self._server("secretary")
        try:
            initialize = await server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                }
            )
            resources = await server.handle_request(
                {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}}
            )
            templates = await server.handle_request(
                {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}}
            )
        finally:
            await server.close()

        self.assertEqual(initialize["result"]["capabilities"], {"tools": {}, "resources": {}})
        self.assertEqual(resources["result"], {"resources": []})
        self.assertEqual(templates["result"], {"resourceTemplates": []})


if __name__ == "__main__":
    unittest.main()
