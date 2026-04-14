from __future__ import annotations

import os
import tempfile
from importlib import import_module
from unittest import IsolatedAsyncioTestCase, mock

from core.orchestra_agents.backends import sgr as sgr_backend
from core.orchestra_agents.backends.sgr.tool_exec import execute_single
from core.orchestra_agents.tests.template_helpers import (
    sgr_fake_omniroute,
    sgr_responses,
)

BackendConfig = dict[str, object]
support = import_module("core.orchestra_agents.tests.sgr_wave1_support")


class _BaseSGRBackendTests(IsolatedAsyncioTestCase):
    backend_config: BackendConfig = {
        "max_reasoning_steps": 6,
        "max_direct_text_retries": 1,
    }
    system_prompt = "Use MCP tools."

    async def asyncSetUp(self) -> None:
        self.previous_env = {
            support.OMNIROUTE_URL_KEY: os.environ.get(
                support.OMNIROUTE_URL_KEY,
            ),
            support.OMNIROUTE_API_KEY: os.environ.get(
                support.OMNIROUTE_API_KEY,
            ),
        }

        self.omniroute = sgr_fake_omniroute.FakeOmniRoute()
        await self.omniroute.start()
        os.environ[support.OMNIROUTE_URL_KEY] = self.omniroute.base_url
        os.environ[support.OMNIROUTE_API_KEY] = "omniroute-test-key"
        self._working_dir_ctx = tempfile.TemporaryDirectory()
        self.backend = sgr_backend.SGRMinimaxBackend(
            agent_slug=support.SGR_AGENT_SLUG,
            backend_type="sgr_minimax",
            working_dir=self._working_dir_ctx.name,
            config=self.backend_config,
            system_prompt=self.system_prompt,
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


class SGRWave1Tests(_BaseSGRBackendTests):
    backend_config: BackendConfig = {
        "route_policy": "minimax_only",
        "model": "MiniMax-M2.7",
        "react_to_inactive": True,
        "max_reasoning_steps": 6,
        "max_direct_text_retries": 1,
    }
    system_prompt = "Use available MCP tools for outward communication."

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._fake_mcp = support.FakeMCPServer()
        sgr_backend.configure_mcp_tools(
            self.backend,
            {"send_telegram_message": self._fake_mcp},
        )

    async def test_response_required_event_without_action(self) -> None:
        self.omniroute.enqueue(sgr_responses._text_response("Thinking..."))
        self.omniroute.enqueue(sgr_responses._text_response("Still thinking..."))
        delivery = support.message_delivery(
            "delivery-no-action",
            "event-no-action",
        )

        dispatch_result = await self.backend.handle_events(delivery)

        self.assertTrue(dispatch_result.accepted)
        self.assertEqual(dispatch_result.details["reason"], "no_tool_action_emitted")
        self.assertTrue(dispatch_result.details["no_action_warning"])
        self.assertTrue(dispatch_result.details["direct_text_ignored"])

    async def test_tool_exec_error_structured(self) -> None:
        fake_server = mock.AsyncMock()
        fake_server.handle_tools_call.side_effect = RuntimeError("boom")
        self.backend._mcp_servers["bad_tool"] = fake_server

        outcome = await execute_single(
            self.backend,
            support.tool_call("bad_tool", "tool-error-1"),
        )

        self.assertEqual(outcome.tool_name, "bad_tool")
        self.assertEqual(outcome.error, "boom")
        self.assertEqual(outcome.result_text, "Error: boom")


class SGRMCPRegistrationTests(_BaseSGRBackendTests):
    """Tests for MCP tool registration."""

    async def test_multi_tool_registration(self) -> None:
        mcp_loader = support.load_mcp_loader()
        fake = support.FakeMCPServer()
        state = support.RegistrationState()
        entry = {support.NAME_KEY: "fallback"}
        defs = [
            {support.NAME_KEY: "a"},
            {support.NAME_KEY: "b"},
        ]
        mcp_loader._register_tools(
            fake,
            entry,
            defs,
            state.servers,
            state.schemas,
        )
        self.assertIn("a", state.servers)
        self.assertIn("b", state.servers)
        self.assertNotIn("fallback", state.servers)

    async def test_fallback_registration(self) -> None:
        mcp_loader = support.load_mcp_loader()
        fake = support.FakeMCPServer()
        state = support.RegistrationState()
        mcp_loader._register_tools(
            fake,
            {support.NAME_KEY: "my_tool"},
            [],
            state.servers,
            state.schemas,
        )

        self.assertIn("my_tool", state.servers)

    async def test_memory_manifest_loads_tool_definitions(self) -> None:
        tool_defs = support.load_mcp_loader().load_mcp_from_config(
            {
                "mcp_servers": [
                    {
                        support.NAME_KEY: "orchestra_memory",
                        "module": "core.orchestra_memory.mcp.server",
                        "class": "OrchestraMemoryMCPServer",
                        "schema_fn": "orchestra_memory_tool_definitions",
                    }
                ]
            },
            agent_slug="sgr",
        )[1]

        self.assertEqual(
            {tool_def["name"] for tool_def in tool_defs},
            support.MEMORY_TOOLS,
        )

    async def test_manifest_loads_orchestra_memory_server(self) -> None:
        manifest = {
            "mcp_servers": [
                {
                    support.NAME_KEY: "orchestra_memory",
                    "module": "core.orchestra_memory.mcp.server",
                    "class": "OrchestraMemoryMCPServer",
                    "schema_fn": "orchestra_memory_tool_definitions",
                }
            ]
        }

        servers, schemas = support.load_mcp_loader().load_mcp_from_config(
            manifest,
            agent_slug="sgr",
        )

        self.assertTrue(support.MEMORY_TOOLS.issubset(set(servers)))
        self.assertTrue(hasattr(servers["memory_remember"], "handle_tools_call"))
        self.assertEqual(
            {tool_def["name"] for tool_def in schemas},
            support.MEMORY_TOOLS,
        )


class SGRSessionResetTests(_BaseSGRBackendTests):
    """Tests for session reset behavior."""

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


class SGRSessionTurnCleanupTests(_BaseSGRBackendTests):
    async def test_session_history_records_event_turns(self) -> None:
        self.omniroute.enqueue(sgr_responses._text_response("Think"))
        self.omniroute.enqueue(sgr_responses._text_response("More"))
        delivery = support.message_delivery("d-clean", "e-clean")
        await self.backend.handle_events(delivery)
        self.assertTrue(self.backend._chat_history.messages_for_session("from:secretary"))

    async def test_session_key_cleared_after_turn_failure(self) -> None:
        with mock.patch.object(
            self.backend._llm,
            "chat_completion",
            new=mock.AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                await self.backend.handle_events(
                    support.message_delivery("d-fail", "e-fail"),
                )

        self.assertEqual(self.backend._chat_history.messages_for_session("from:secretary"), [])

    async def test_last_peer_preserved_in_result_details(self) -> None:
        self.omniroute.enqueue(sgr_responses._text_response("Think"))
        self.omniroute.enqueue(sgr_responses._text_response("More"))

        dispatch_result = await self.backend.handle_events(
            support.message_delivery("d-peer", "e-peer"),
        )

        self.assertEqual(dispatch_result.details["peer_agent_slug"], "secretary")
