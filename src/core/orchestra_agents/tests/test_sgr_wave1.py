from __future__ import annotations

import os
import tempfile
from typing import Any
from unittest import IsolatedAsyncioTestCase, main, mock

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from agents.sgr.agent_runtime.tool_exec import execute_single
from core.orchestra_agents.runtime import EventDelivery
from core.orchestra_agents.tests import test_sgr_example as _fixtures


class SGRWave1Tests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "OMNIROUTE_URL": os.environ.get("OMNIROUTE_URL"),
            "OMNIROUTE_API_KEY": os.environ.get("OMNIROUTE_API_KEY"),
        }

        self.omniroute = _fixtures.FakeOmniRoute()
        await self.omniroute.start()
        os.environ["OMNIROUTE_URL"] = self.omniroute.base_url
        os.environ["OMNIROUTE_API_KEY"] = "omniroute-test-key"
        self._working_dir_ctx = tempfile.TemporaryDirectory()
        self.backend = SGRMinimaxBackend(
            agent_slug="sgr",
            backend_type="sgr_minimax",
            working_dir=self._working_dir_ctx.name,
            config={
                "route_policy": "minimax_only",
                "model": "MiniMax-M2.7",
                "react_to_inactive": True,
                "max_reasoning_steps": 6,
                "max_direct_text_retries": 1,
            },
            system_prompt="Use available MCP tools for outward communication.",
        )
        self._fake_mcp = _FakeMCPServer()
        from agents.sgr.agent_runtime.backend import configure_mcp_tools

        configure_mcp_tools(
            self.backend,
            {"send_telegram_message": self._fake_mcp},
        )
        await self.backend.on_start()

    async def asyncTearDown(self) -> None:
        await self.backend.on_shutdown()
        await self.omniroute.stop()
        self._working_dir_ctx.cleanup()
        for key, prev_val in self.previous_env.items():
            if prev_val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev_val

    async def test_response_required_event_without_action(self) -> None:
        self.omniroute.enqueue(_fixtures._text_response("Thinking..."))
        self.omniroute.enqueue(_fixtures._text_response("Still thinking..."))
        delivery = _message_delivery("delivery-no-action", "event-no-action")

        result = await self.backend.handle_events(delivery)

        self.assertTrue(result.accepted)
        self.assertEqual(result.details["reason"], "no_tool_action_emitted")
        self.assertTrue(result.details["no_action_warning"])
        self.assertTrue(result.details["direct_text_ignored"])

    async def test_tool_execution_error_returns_structured_error(self) -> None:
        fake_server = mock.AsyncMock()
        fake_server.handle_tools_call.side_effect = RuntimeError("boom")
        self.backend._mcp_servers["bad_tool"] = fake_server

        outcome = await execute_single(
            self.backend,
            _tool_call(name="bad_tool", arguments={}, call_id="tool-error-1"),
        )

        self.assertEqual(outcome.tool_name, "bad_tool")
        self.assertEqual(outcome.error, "boom")
        self.assertEqual(outcome.result_text, "Error: boom")


class SGRMCPAndSessionTests(IsolatedAsyncioTestCase):
    """Tests for MCP tool registration and session lifecycle."""

    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "OMNIROUTE_URL": os.environ.get("OMNIROUTE_URL"),
            "OMNIROUTE_API_KEY": os.environ.get("OMNIROUTE_API_KEY"),
        }
        self.omniroute = _fixtures.FakeOmniRoute()
        await self.omniroute.start()
        os.environ["OMNIROUTE_URL"] = self.omniroute.base_url
        os.environ["OMNIROUTE_API_KEY"] = "omniroute-test-key"
        self._working_dir_ctx = tempfile.TemporaryDirectory()
        self.backend = SGRMinimaxBackend(
            agent_slug="sgr",
            backend_type="sgr_minimax",
            working_dir=self._working_dir_ctx.name,
            config={"max_reasoning_steps": 6, "max_direct_text_retries": 1},
            system_prompt="Use MCP tools.",
        )
        await self.backend.on_start()

    async def asyncTearDown(self) -> None:
        await self.backend.on_shutdown()
        await self.omniroute.stop()
        self._working_dir_ctx.cleanup()
        for key, prev_val in self.previous_env.items():
            if prev_val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev_val

    async def test_multi_tool_registration(self) -> None:
        from agents.sgr.agent_runtime.mcp_loader import _register_server_tools

        fake = _FakeMCPServer()
        servers: dict[str, Any] = {}
        schemas: list[dict[str, Any]] = []
        entry = {"name": "fallback"}
        defs = [{"name": "a"}, {"name": "b"}]
        _register_server_tools(fake, entry, defs, servers, schemas)
        self.assertIn("a", servers)
        self.assertIn("b", servers)
        self.assertNotIn("fallback", servers)

    async def test_fallback_registration(self) -> None:
        from agents.sgr.agent_runtime.mcp_loader import _register_server_tools

        fake = _FakeMCPServer()
        servers: dict[str, Any] = {}
        schemas: list[dict[str, Any]] = []
        _register_server_tools(fake, {"name": "my_tool"}, [], servers, schemas)
        self.assertIn("my_tool", servers)

    async def test_reset_clears_only_session(self) -> None:
        self.backend._chat_history.record_turn(
            session_key="chat:a",
            user_text="A",
            assistant_text="reply A",
        )
        self.backend._chat_history.record_turn(
            session_key="chat:b",
            user_text="B",
            assistant_text="reply B",
        )
        await self.backend.reset_session("chat:a")
        self.assertEqual(self.backend._chat_history.messages_for_session("chat:a"), [])
        self.assertEqual(len(self.backend._chat_history.messages_for_session("chat:b")), 2)

    async def test_reset_session_preserves_other_sessions(self) -> None:
        self.backend._chat_history.record_turn(
            session_key="chat:x",
            user_text="X",
            assistant_text="reply X",
        )
        self.backend._chat_history.record_turn(
            session_key="chat:y",
            user_text="Y",
            assistant_text="reply Y",
        )
        await self.backend.reset_session("chat:x")
        self.assertEqual(self.backend._chat_history.messages_for_session("chat:x"), [])
        self.assertEqual(len(self.backend._chat_history.messages_for_session("chat:y")), 2)


class SGRSessionTurnCleanupTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "OMNIROUTE_URL": os.environ.get("OMNIROUTE_URL"),
            "OMNIROUTE_API_KEY": os.environ.get("OMNIROUTE_API_KEY"),
        }
        self.omniroute = _fixtures.FakeOmniRoute()
        await self.omniroute.start()
        os.environ["OMNIROUTE_URL"] = self.omniroute.base_url
        os.environ["OMNIROUTE_API_KEY"] = "omniroute-test-key"
        self._working_dir_ctx = tempfile.TemporaryDirectory()
        self.backend = SGRMinimaxBackend(
            agent_slug="sgr",
            backend_type="sgr_minimax",
            working_dir=self._working_dir_ctx.name,
            config={"max_reasoning_steps": 6, "max_direct_text_retries": 1},
            system_prompt="Use MCP tools.",
        )
        await self.backend.on_start()

    async def asyncTearDown(self) -> None:
        await self.backend.on_shutdown()
        await self.omniroute.stop()
        self._working_dir_ctx.cleanup()
        for key, prev_val in self.previous_env.items():
            if prev_val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev_val

    async def test_session_history_records_event_turns(self) -> None:
        self.omniroute.enqueue(_fixtures._text_response("Think"))
        self.omniroute.enqueue(_fixtures._text_response("More"))
        delivery = _message_delivery("d-clean", "e-clean")
        await self.backend.handle_events(delivery)
        self.assertTrue(self.backend._chat_history.messages_for_session("from:secretary"))

    async def test_session_key_cleared_after_turn_failure(self) -> None:
        with mock.patch.object(
            self.backend._llm,
            "chat_completion",
            new=mock.AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                await self.backend.handle_events(_message_delivery("d-fail", "e-fail"))

        self.assertEqual(self.backend._chat_history.messages_for_session("from:secretary"), [])

    async def test_last_peer_preserved_in_result_details(self) -> None:
        self.omniroute.enqueue(_fixtures._text_response("Think"))
        self.omniroute.enqueue(_fixtures._text_response("More"))

        result = await self.backend.handle_events(_message_delivery("d-peer", "e-peer"))

        self.assertEqual(result.details["peer_agent_slug"], "secretary")


if __name__ == "__main__":
    main()


class _FakeMCPServer:
    """Minimal MCP server stub for testing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def handle_tools_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"name": name, "arguments": arguments})
        return {
            "content": [{"type": "text", "text": "ok"}],
            "structuredContent": {"ok": True},
        }

    async def close(self) -> None:
        """No-op close for testing."""


def _message_delivery(delivery_id: str, event_id: str) -> EventDelivery:
    return EventDelivery.from_dict(
        {
            "delivery_id": delivery_id,
            "events": [
                {
                    "event_id": event_id,
                    "thread_id": None,
                    "root_thread_id": None,
                    "parent_thread_id": None,
                    "owner_agent_slug": None,
                    "sequence_no": 10,
                    "event_kind": "message",
                    "notification_status": None,
                    "from_agent_slug": "secretary",
                    "to_agent_slug": "sgr",
                    "message_text": "Please confirm receipt.",
                    "interrupts_runtime": True,
                    "requires_response": True,
                    "created_at": "2026-04-03T07:10:00Z",
                },
            ],
        },
    )


def _tool_call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": "{}",
        },
    }
