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
from core.orchestra_thread.mcp.server import OrchestraThreadsMCPServer
from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness

_SLUG_SECRETARY = "secretary"
_SLUG_ORCHESTRA = "orchestra"
_KEY_THREAD = "thread"
_KEY_THREAD_ID = "thread_id"
_TOOL_SEND = "thread_send"
_KEY_MESSAGE = "message"


def _structured(mcp_result: dict[str, Any]) -> dict[str, Any]:
    return dict(mcp_result["structuredContent"])


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
        {
            "from_agent_slug": _SLUG_SECRETARY,
            "to_agent_slug": _SLUG_ORCHESTRA,
            "message_text": "Prepare a short update.",
        },
    )
    thread_id = str(root[_KEY_THREAD][_KEY_THREAD_ID])
    await harness.wait_for(
        lambda: len(orchestra.events) >= 1,
        message="orchestra did not receive the initial root-thread message",
    )
    write_active_context(
        {
            _KEY_THREAD_ID: thread_id,
            "root_thread_id": thread_id,
            "parent_thread_id": None,
            "source_agent_slug": _SLUG_SECRETARY,
            "target_agent_slug": _SLUG_ORCHESTRA,
            "owner_agent_slug": _SLUG_SECRETARY,
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
        self.secretary = await self.harness.add_agent(_SLUG_SECRETARY)
        self.orchestra = await self.harness.add_agent(_SLUG_ORCHESTRA)
        self.specialist = await self.harness.add_agent("specialist")

    async def asyncTearDown(self) -> None:
        clear_active_context()
        active_context_module.ACTIVE_CONTEXT_PATH = self.original_context_path
        await self.harness.stop()


class MCPSendToolTests(MCPServerSetupMixin):
    """Tests for thread_send and thread_current MCP tools."""

    async def test_send_creates_root(self) -> None:
        async with _server_ctx(self.harness, _SLUG_SECRETARY) as server:
            send_result = await server.handle_tools_call(
                name=_TOOL_SEND,
                arguments={
                    "target_agent_slug": _SLUG_ORCHESTRA,
                    _KEY_MESSAGE: "Prepare a short update.",
                },
            )
        payload = _structured(send_result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "thread_send")
        self.assertEqual(payload["route"], "created_root")
        self.assertEqual(payload["peer_agent_slug"], _SLUG_ORCHESTRA)
        self.assertIsNotNone(payload[_KEY_THREAD_ID])

        await self._close_root(str(payload[_KEY_THREAD_ID]))

    async def test_current_reply_and_child(self) -> None:
        thread_id = await _create_root_context(self.harness, self.orchestra)
        async with _server_ctx(self.harness, _SLUG_ORCHESTRA) as server:
            await self._verify_current(server, thread_id)
            await self._verify_reply(server, thread_id)
            await self._verify_child(server, thread_id)
        await self._close_root(thread_id)

    async def test_current_hides_actions_for_blocked_peer(self) -> None:
        await self.harness.request_json(
            method="POST",
            path="/agents/register",
            payload={
                "agent_slug": _SLUG_ORCHESTRA,
                "base_url": self.orchestra.base_url,
                "metadata": {
                    "allowed_peer_agent_slugs": [
                        _SLUG_SECRETARY,
                        "dev",
                        "qa",
                        "devops",
                    ]
                },
            },
        )
        root = await self.harness.send_message(
            {
                "from_agent_slug": "human",
                "to_agent_slug": _SLUG_ORCHESTRA,
                "message_text": "Blocked peer should not be advertised as replyable.",
            }
        )
        thread_id = str(root[_KEY_THREAD][_KEY_THREAD_ID])
        await self.harness.wait_for(
            lambda: len(self.orchestra.events) >= 1,
            message="orchestra did not receive blocked-peer root-thread message",
        )
        write_active_context(
            {
                _KEY_THREAD_ID: thread_id,
                "root_thread_id": thread_id,
                "parent_thread_id": None,
                "source_agent_slug": "human",
                "target_agent_slug": _SLUG_ORCHESTRA,
                "owner_agent_slug": "human",
            }
        )

        async with _server_ctx(self.harness, _SLUG_ORCHESTRA) as server:
            current = _structured(
                await server.handle_tools_call(name="thread_current", arguments={}),
            )

        self.assertTrue(current["active"])
        self.assertEqual(current[_KEY_THREAD_ID], thread_id)
        self.assertEqual(current["peer_agent_slug"], "human")
        self.assertEqual(current["allowed_actions"], [])

    async def _verify_current(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        current = _structured(
            await server.handle_tools_call(name="thread_current", arguments={}),
        )
        self.assertTrue(current["active"])
        self.assertEqual(current[_KEY_THREAD_ID], thread_id)
        self.assertEqual(current["peer_agent_slug"], _SLUG_SECRETARY)
        self.assertIn(_TOOL_SEND, current["allowed_actions"])

    async def _verify_reply(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        reply = _structured(
            await server.handle_tools_call(
                name=_TOOL_SEND,
                arguments={_KEY_MESSAGE: "Done. Here is the update."},
            ),
        )
        self.assertEqual(reply["route"], "reply_current")
        self.assertEqual(reply[_KEY_THREAD_ID], thread_id)

    async def _verify_child(
        self,
        server: OrchestraThreadsMCPServer,
        thread_id: str,
    ) -> None:
        child = _structured(
            await server.handle_tools_call(
                name=_TOOL_SEND,
                arguments={
                    "target_agent_slug": "specialist",
                    _KEY_MESSAGE: "Check one detail.",
                },
            ),
        )
        self.assertEqual(child["route"], "created_child")
        self.assertNotEqual(child[_KEY_THREAD_ID], thread_id)

    async def _close_root(self, thread_id: str) -> None:
        closed = await self.harness.close_thread(
            owner_agent=self.secretary,
            peer_agent=self.orchestra,
            thread_id=thread_id,
            message_text="Closing MCP test thread.",
        )
        self.assertEqual(closed[_KEY_THREAD]["status"], "closed")


class MCPStatusAndProtocolTests(MCPServerSetupMixin):
    """Tests for status, expand, guide, and protocol surface."""

    async def test_status_and_expand(self) -> None:
        thread_id = await _create_root_context(self.harness, self.orchestra)
        async with _server_ctx(self.harness, _SLUG_ORCHESTRA) as server:
            await self._verify_status(server, thread_id)
            await self._verify_expand(server, thread_id)
        await self._close_root(thread_id)

    async def test_guide_returns_workflow(self) -> None:
        async with _server_ctx(self.harness, _SLUG_SECRETARY) as server:
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
        async with _server_ctx(self.harness, _SLUG_SECRETARY) as server:
            init_resp = await server.handle_request(
                _init_request(),
            )
            resources = await server.handle_request(
                {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
            )
            templates = await server.handle_request(
                {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}},
            )
        assert init_resp is not None
        assert resources is not None
        assert templates is not None
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
                arguments={"status": "review", _KEY_MESSAGE: "Ready for handoff."},
            ),
        )
        self.assertTrue(status["ok"])
        self.assertEqual(status[_KEY_THREAD_ID], thread_id)
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
        self.assertEqual(latest[_KEY_THREAD][_KEY_THREAD_ID], thread_id)
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
        self.assertEqual(closed[_KEY_THREAD]["status"], "closed")


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
