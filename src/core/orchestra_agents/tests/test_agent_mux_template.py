from __future__ import annotations

import os
import unittest
from typing import Any, cast

from core.orchestra_agents import runtime as runtime_contract
from core.orchestra_agents.tests.template_helpers.assertions import (
    _assert_completed_status,
    _assert_direct_capture,
    _assert_failed_dispatch,
    _assert_process_active,
    _assert_process_stopped,
    _dispatch_and_assert_completed,
)
from core.orchestra_agents.tests.template_helpers.backend_ops import (
    _delivery,
    _read_capture,
    _start_backend,
)
from core.orchestra_agents.tests.template_helpers.context_assertions import (
    _assert_context_lifecycle,
)
from core.orchestra_agents.tests.template_helpers.context_ops import (
    _context_lifecycle_snapshots,
    _prompt_after_two_turns,
)
from core.orchestra_agents.tests.template_helpers.fixture import (
    TemplateFixture,
    build_template_fixture,
)


class AgentMuxTemplateBase(unittest.IsolatedAsyncioTestCase):
    fixture: TemplateFixture

    async def asyncSetUp(self) -> None:
        self.fixture = build_template_fixture(self)


class AgentMuxTemplateDispatchTests(AgentMuxTemplateBase):
    async def test_direct_event_runs_mux_backend(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        backend = cast(
            Any,
            await _start_backend(
                self,
                self.fixture,
                require_tool_call_for_response=True,
                include_mcp_server=True,
            ),
        )
        await _dispatch_and_assert_completed(
            self,
            backend,
            _delivery(),
        )

        capture = _read_capture(self.fixture.capture_path)
        _assert_direct_capture(self, backend, capture)

        status = await backend.last_status()
        _assert_completed_status(self, backend, status)

    async def test_mcp_servers_are_optional(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        backend = cast(Any, await _start_backend(self, self.fixture))
        await _dispatch_and_assert_completed(
            self,
            backend,
            _delivery(),
        )

        capture = _read_capture(self.fixture.capture_path)
        self.assertNotIn("[mcp_servers.", cast(str, capture["codex_config"]))

    async def test_memory_mcp_server_rendered_into_codex_config(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        backend = cast(
            Any,
            await _start_backend(
                self,
                self.fixture,
                include_mcp_server=True,
            ),
        )
        await _dispatch_and_assert_completed(
            self,
            backend,
            _delivery(),
        )
        capture = _read_capture(self.fixture.capture_path)
        codex_config = cast(str, capture["codex_config"])
        self.assertIn("[mcp_servers.orchestra_memory]", codex_config)
        self.assertIn("ORCHESTRA_AGENT_SLUG", codex_config)
        self.assertIn("ORCHESTRA_MEMORY_URL", codex_config)

    async def test_sanitize_reply_text_strips_think_blocks(self) -> None:
        backend_module = cast(Any, self.fixture.backend_module)
        self.assertEqual(
            backend_module._sanitize_reply_text("<think>internal</think>\n\nREADY"),
            "READY",
        )

    async def test_plain_text_rejected_by_tool_policy(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "reply"
        backend = cast(
            Any,
            await _start_backend(
                self,
                self.fixture,
                require_tool_call_for_response=True,
                max_attempts=1,
            ),
        )
        await backend.handle_events(_delivery())
        await _assert_failed_dispatch(self, backend)
        self.assertIn("without any tool call", backend.last_dispatch_reason or "")

    async def test_stop_interrupts_active_dispatch(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "reply"
        os.environ["FAKE_AGENT_MUX_SLEEP"] = "5"
        backend = cast(Any, await _start_backend(self, self.fixture))
        await backend.handle_events(_delivery())
        await _assert_process_active(self, backend)

        stop_payload = await backend.stop(
            runtime_contract.StopRequest(
                reason="stop requested",
                thread_id=None,
                parent_thread_id=None,
            )
        )
        self.assertEqual(stop_payload["cleared_queue_events"], 0)
        await _assert_process_stopped(self, backend)


class AgentMuxTemplateContextTests(AgentMuxTemplateBase):
    async def test_context_id_persists_until_clear(self) -> None:
        before, cleared, restarted = await _context_lifecycle_snapshots(
            self.fixture,
            requested_by="tester",
        )
        _assert_context_lifecycle(self, before, cleared, restarted)

    async def test_context_memory_survives_turns(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        prompt, recent_entries = await _prompt_after_two_turns(
            self,
            self.fixture,
        )
        self.assertIn("Prepare the update.", prompt)
        self.assertIn("What did I ask before?", prompt)
        self.assertIn("mcp_tool_call", prompt)
        self.assertGreaterEqual(len(recent_entries), 3)
