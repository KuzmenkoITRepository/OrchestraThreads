from __future__ import annotations

import os
import tempfile
import unittest
from typing import Any

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from core.orchestra_agents.tests.template_helpers.sgr_assertions import (
    _assert_inactive_delivery_result,
    _assert_message_event_result,
)
from core.orchestra_agents.tests.template_helpers.sgr_fake_mcp import FakeToolMCPServer
from core.orchestra_agents.tests.template_helpers.sgr_fake_omniroute import FakeOmniRoute
from core.orchestra_agents.tests.template_helpers.sgr_fake_thread import FakeThreadService
from core.orchestra_agents.tests.template_helpers.sgr_responses import (
    _base_event_payload,
    _build_delivery,
    _inactive_status_tool_response,
    _text_response,
    _tool_response,
)

_THREAD_ID = "thread-1"
_SGR_SLUG = "sgr"
_SECRETARY_SLUG = "secretary"


class _SGRMinimaxBackendBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "OMNIROUTE_URL": os.environ.get("OMNIROUTE_URL"),
            "OMNIROUTE_API_KEY": os.environ.get("OMNIROUTE_API_KEY"),
        }

        self.thread_service = FakeThreadService()
        self.thread_service.compact_threads[_THREAD_ID] = _compact_thread_payload()
        self.omniroute = FakeOmniRoute()
        self._working_dir_ctx = tempfile.TemporaryDirectory()
        await self.thread_service.start()
        await self.omniroute.start()
        os.environ["OMNIROUTE_URL"] = self.omniroute.base_url
        os.environ["OMNIROUTE_API_KEY"] = "omniroute-test-key"
        self.backend = SGRMinimaxBackend(
            agent_slug=_SGR_SLUG,
            backend_type="sgr_minimax",
            working_dir=self._working_dir_ctx.name,
            config={
                "route_policy": "minimax_only",
                "model": "MiniMax-M2.7",
                "react_to_inactive": True,
                "max_reasoning_steps": 6,
                "max_direct_text_retries": 1,
            },
            system_prompt="Use thread_send or thread_status via OrchestraThreads MCP tools.",
        )
        self._fake_mcp = FakeToolMCPServer(self.thread_service)
        from agents.sgr.agent_runtime.backend import configure_mcp_tools

        configure_mcp_tools(
            self.backend,
            {
                "thread_send": self._fake_mcp,
                "thread_status": self._fake_mcp,
                "thread_current": self._fake_mcp,
                "thread_expand": self._fake_mcp,
            },
        )
        await self.backend.on_start()

    async def asyncTearDown(self) -> None:
        await self.backend.on_shutdown()
        await self.omniroute.stop()
        await self.thread_service.stop()
        self._working_dir_ctx.cleanup()
        for key, env_value in self.previous_env.items():
            if env_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = env_value


class SGRMinimaxMessageEventTests(_SGRMinimaxBackendBase):
    async def test_message_event_triggers_mcp_tools(self) -> None:
        self.omniroute.enqueue(
            _tool_response(tool_name="thread_current", arguments={}, call_id="call-current")
        )
        self.omniroute.enqueue(
            _tool_response(
                tool_name="thread_send",
                arguments={
                    "message": "Draft ready for handoff.",
                    "client_request_id": "tool-reply-1",
                },
                call_id="call-send",
            )
        )
        self.omniroute.enqueue(_text_response("Turn complete."))

        delivery = _build_delivery(delivery_id="delivery-1", event_payload=_base_event_payload())
        dispatch = await self.backend.handle_events(delivery)
        status = await self.backend.last_status()
        observed = _collect_message_observed(dispatch, status, self.omniroute, self.thread_service)
        _assert_message_event_result(self, observed)
        _assert_first_request_shape(self, self.omniroute)
        self.assertIn("thread_send", dispatch.details["used_tools"])

    async def test_direct_text_ignored_before_tool(self) -> None:
        self.omniroute.enqueue(_text_response("I would answer with a short summary."))
        self.omniroute.enqueue(
            _tool_response(
                tool_name="thread_send",
                arguments={
                    "message": "Here is the requested short summary.",
                    "client_request_id": "tool-reply-2",
                },
                call_id="call-send",
            )
        )
        self.omniroute.enqueue(_text_response("Done."))

        delivery = _build_delivery(delivery_id="delivery-1", event_payload=_base_event_payload())
        dispatch = await self.backend.handle_events(delivery)

        self.assertEqual(
            (
                dispatch.accepted,
                len(self.thread_service.message_calls),
                len(self.omniroute.chat_requests),
            ),
            (True, 1, 3),
        )
        _assert_direct_text_reminder(self, self.omniroute)
        self.assertTrue(dispatch.details["direct_text_ignored"])

        status = await self.backend.last_status()
        self.assertEqual(
            (status["last_reply_preview"], status["last_ignored_output_preview"]),
            ("Here is the requested short summary.", "Done."),
        )


class SGRMinimaxDeliveryEventTests(_SGRMinimaxBackendBase):
    async def test_inactive_event_publishes_status(self) -> None:
        self.omniroute.enqueue(_inactive_status_tool_response())
        self.omniroute.enqueue(_text_response("Done."))

        inactive_event = _base_event_payload()
        inactive_event.update(
            {
                "event_id": "event-2",
                "sequence_no": 4,
                "event_kind": "inactive",
                "from_agent_slug": "orchestra_threads",
                "message_text": "",
                "requires_response": False,
                "created_at": "2026-04-03T07:01:00Z",
            }
        )
        delivery = _build_delivery(delivery_id="delivery-2", event_payload=inactive_event)

        dispatch = await self.backend.handle_events(delivery)

        _assert_inactive_delivery_result(self, dispatch, self.thread_service.notification_calls)

        status = await self.backend.last_status()
        self.assertEqual(status["last_published_status"], "in_progress")
        self.assertEqual(status["last_status_preview"], "Still working on the requested summary.")

    async def test_duplicate_delivery_skips_tool(self) -> None:
        self.omniroute.enqueue(
            _tool_response(tool_name="thread_current", arguments={}, call_id="call-current")
        )
        self.omniroute.enqueue(
            _tool_response(
                tool_name="thread_send",
                arguments={
                    "message": "Draft ready for handoff.",
                    "client_request_id": "tool-reply-3",
                },
                call_id="call-send",
            )
        )
        self.omniroute.enqueue(_text_response("Turn complete."))

        delivery = _build_delivery(delivery_id="delivery-1", event_payload=_base_event_payload())
        first = await self.backend.handle_events(delivery)
        second = await self.backend.handle_events(delivery)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertTrue(second.duplicate)
        self.assertEqual(len(self.thread_service.message_calls), 1)
        self.assertEqual(len(self.omniroute.chat_requests), 3)

    async def test_notification_event_processed(self) -> None:
        self.omniroute.enqueue(_text_response("Noted. I will keep that in mind."))
        self.omniroute.enqueue(_text_response("Nothing else to send right now."))
        delivery = _build_delivery(
            delivery_id="delivery-3",
            event_payload={
                "event_id": "event-3",
                "thread_id": _THREAD_ID,
                "event_kind": "notification",
                "notification_status": "review",
                "from_agent_slug": _SECRETARY_SLUG,
                "to_agent_slug": _SGR_SLUG,
                "message_text": "Review is ready.",
                "interrupts_runtime": True,
                "requires_response": False,
            },
        )

        dispatch = await self.backend.handle_events(delivery)

        self.assertTrue(dispatch.accepted)
        self.assertEqual(dispatch.details["reason"], "no_tool_action_emitted")
        self.assertNotIn("event_metadata", dispatch.details)
        self.assertEqual(len(self.thread_service.message_calls), 0)
        self.assertEqual(len(self.thread_service.notification_calls), 0)
        self.assertEqual(len(self.omniroute.chat_requests), 2)


def _compact_thread_payload() -> dict[str, Any]:
    return {
        "thread_id": _THREAD_ID,
        "root_thread_id": _THREAD_ID,
        "parent_thread_id": None,
        "scope": "root",
        "status": "open",
        "owner_agent_slug": _SECRETARY_SLUG,
        "participant_a_agent_slug": _SECRETARY_SLUG,
        "participant_b_agent_slug": _SGR_SLUG,
        "last_event_kind": "message",
        "last_event_from_agent_slug": _SECRETARY_SLUG,
        "last_event_to_agent_slug": _SGR_SLUG,
        "last_event_message_preview": "Please prepare the summary.",
    }


def _collect_message_observed(
    dispatch: Any,
    status: dict[str, Any],
    omniroute: FakeOmniRoute,
    thread_service: FakeThreadService,
) -> dict[str, Any]:
    first_payload = omniroute.chat_requests[0]["payload"]
    return {
        "accepted": dispatch.accepted,
        "chat_requests": len(omniroute.chat_requests),
        "model": first_payload["model"],
        "message": thread_service.message_calls[0]["message"],
        "sent": dispatch.details["messages_sent"],
        "tool_calls": dispatch.details["tool_calls"],
        "last_peer": status["last_peer_agent_slug"],
        "last_reply": status["last_reply_preview"],
        "last_action": status["last_action_emitted"],
    }


def _assert_first_request_shape(
    test_case: unittest.IsolatedAsyncioTestCase,
    omniroute: FakeOmniRoute,
) -> None:
    first_req = omniroute.chat_requests[0]
    test_case.assertEqual(first_req["path"], "/v1/chat/completions")
    test_case.assertTrue(first_req["payload"]["tools"])
    test_case.assertEqual(
        first_req["headers"].get("Authorization"),
        "Bearer omniroute-test-key",
    )


def _assert_direct_text_reminder(
    test_case: unittest.IsolatedAsyncioTestCase,
    omniroute: FakeOmniRoute,
) -> None:
    second_payload = omniroute.chat_requests[1]["payload"]
    reminders = [
        str(msg.get("content") or "")
        for msg in second_payload["messages"]
        if isinstance(msg, dict) and msg.get("role") == "system"
    ]
    test_case.assertTrue(
        any("Direct assistant text helps you think" in reminder for reminder in reminders)
    )


if __name__ == "__main__":
    unittest.main()
