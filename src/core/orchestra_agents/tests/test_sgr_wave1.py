from __future__ import annotations

import json
import os
import tempfile
from unittest import IsolatedAsyncioTestCase, main, mock

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from agents.sgr.agent_runtime.tool_exec import execute_single
from core.orchestra_agents.runtime import EventDelivery
from core.orchestra_agents.tests import test_sgr_example as _fixtures
from core.orchestra_thread import active_context as active_context_module


class SGRWave1Tests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "ORCHESTRA_THREADS_URL": os.environ.get("ORCHESTRA_THREADS_URL"),
            "LLM_PROXY_URL": os.environ.get("LLM_PROXY_URL"),
            "LLM_PROXY_ENABLED": os.environ.get("LLM_PROXY_ENABLED"),
            "LLM_PROXY_API_KEY": os.environ.get("LLM_PROXY_API_KEY"),
        }
        from pathlib import Path

        self.context_path = (
            Path(tempfile.mkdtemp(prefix="sgr_runtime_wave1_ctx_")) / "active_context.json"
        )
        self.original_context_path = active_context_module.ACTIVE_CONTEXT_PATH
        active_context_module.ACTIVE_CONTEXT_PATH = self.context_path

        self.thread_service = _fixtures.FakeThreadService()
        self.thread_service.compact_threads["thread-1"] = {
            "thread_id": "thread-1",
            "root_thread_id": "thread-1",
            "parent_thread_id": None,
            "scope": "root",
            "status": "open",
            "owner_agent_slug": "secretary",
            "participant_a_agent_slug": "secretary",
            "participant_b_agent_slug": "sgr",
            "last_event_kind": "message",
            "last_event_from_agent_slug": "secretary",
            "last_event_to_agent_slug": "sgr",
            "last_event_message_preview": "Please prepare the summary.",
        }
        self.llm_proxy = _fixtures.FakeLLMProxy()
        await self.thread_service.start()
        await self.llm_proxy.start()
        os.environ["ORCHESTRA_THREADS_URL"] = self.thread_service.base_url
        os.environ["LLM_PROXY_URL"] = self.llm_proxy.base_url
        os.environ["LLM_PROXY_ENABLED"] = "true"
        os.environ["LLM_PROXY_API_KEY"] = "llm-proxy"
        self.backend = SGRMinimaxBackend(
            agent_slug="sgr",
            backend_type="sgr_minimax",
            working_dir="/workspace/agents/sgr",
            config={
                "route_policy": "minimax_only",
                "model": "MiniMax-M2.7",
                "guide_view": "compact",
                "heartbeat_interval_seconds": 60,
                "react_to_inactive": True,
                "max_reasoning_steps": 6,
                "max_direct_text_retries": 1,
                "http_endpoint": "http://orchestra-agent-sgr:8787",
            },
            system_prompt="Use thread_send or thread_status via OrchestraThreads MCP tools.",
        )
        await self.backend.on_start()

    async def asyncTearDown(self) -> None:
        await self.backend.on_shutdown()
        await self.llm_proxy.stop()
        await self.thread_service.stop()
        active_context_module.ACTIVE_CONTEXT_PATH = self.original_context_path
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    async def test_response_required_event_without_action_is_graceful(self) -> None:
        self.llm_proxy.enqueue(_fixtures._text_response("I have enough context."))
        self.llm_proxy.enqueue(_fixtures._text_response("I will wait before replying."))
        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-no-action",
                "events": [
                    {
                        "event_id": "event-no-action",
                        "thread_id": "thread-1",
                        "root_thread_id": "thread-1",
                        "parent_thread_id": None,
                        "owner_agent_slug": "secretary",
                        "sequence_no": 10,
                        "event_kind": "message",
                        "notification_status": None,
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Please confirm receipt.",
                        "interrupts_runtime": True,
                        "requires_response": True,
                        "created_at": "2026-04-03T07:10:00Z",
                    }
                ],
            }
        )

        result = await self.backend.handle_events(delivery)

        self.assertTrue(result.accepted)
        self.assertEqual(result.details["reason"], "no_tool_action_emitted")
        self.assertTrue(result.details["no_action_warning"])
        self.assertTrue(result.details["direct_text_ignored"])
        self.assertEqual(len(self.thread_service.message_calls), 0)

    async def test_multiple_events_in_delivery_are_processed(self) -> None:
        _enqueue_multi_event_responses(self.llm_proxy)
        delivery = _multi_event_delivery()

        result = await self.backend.handle_events(delivery)

        self.assertTrue(result.accepted)
        self.assertEqual(result.details["event_ids"], ["event-multi-1", "event-multi-2"])
        self.assertEqual(result.details["statuses_published"], 1)
        self.assertEqual(result.details["messages_sent"], 1)
        self.assertEqual(len(self.thread_service.notification_calls), 1)
        self.assertEqual(len(self.thread_service.message_calls), 1)

    async def test_tool_execution_error_returns_structured_error(self) -> None:
        fake_server = mock.AsyncMock()
        fake_server.handle_tools_call.side_effect = RuntimeError("boom")

        with mock.patch.object(
            self.backend._thread_ops,
            "ensure_mcp_server",
            return_value=fake_server,
        ):
            outcome = await execute_single(
                self.backend,
                {
                    "id": "tool-error-1",
                    "type": "function",
                    "function": {
                        "name": "thread_current",
                        "arguments": json.dumps({}, ensure_ascii=False),
                    },
                },
            )

        self.assertEqual(outcome.tool_name, "thread_current")
        self.assertEqual(outcome.error, "boom")
        self.assertEqual(outcome.result_text, "Error: boom")


if __name__ == "__main__":
    main()


def _multi_event_delivery() -> EventDelivery:
    return EventDelivery.from_dict(
        {
            "delivery_id": "delivery-multi",
            "events": [
                {
                    "event_id": "event-multi-1",
                    "thread_id": "thread-1",
                    "root_thread_id": "thread-1",
                    "parent_thread_id": None,
                    "owner_agent_slug": "secretary",
                    "sequence_no": 11,
                    "event_kind": "inactive",
                    "notification_status": None,
                    "from_agent_slug": "orchestra_threads",
                    "to_agent_slug": "sgr",
                    "message_text": "",
                    "interrupts_runtime": True,
                    "requires_response": False,
                    "created_at": "2026-04-03T07:11:00Z",
                },
                {
                    "event_id": "event-multi-2",
                    "thread_id": "thread-1",
                    "root_thread_id": "thread-1",
                    "parent_thread_id": None,
                    "owner_agent_slug": "secretary",
                    "sequence_no": 12,
                    "event_kind": "message",
                    "notification_status": None,
                    "from_agent_slug": "secretary",
                    "to_agent_slug": "sgr",
                    "message_text": "Please send the final update.",
                    "interrupts_runtime": True,
                    "requires_response": True,
                    "created_at": "2026-04-03T07:12:00Z",
                },
            ],
        }
    )


def _enqueue_multi_event_responses(llm_proxy: _fixtures.FakeLLMProxy) -> None:
    llm_proxy.enqueue(
        _fixtures._tool_response(
            tool_name="thread_status",
            arguments={
                "status": "in_progress",
                "message": "Started working on the first request.",
                "client_request_id": "tool-status-multi-1",
            },
            call_id="call-status-multi-1",
        )
    )
    llm_proxy.enqueue(_fixtures._text_response("Done with the first turn."))
    llm_proxy.enqueue(
        _fixtures._tool_response(
            tool_name="thread_send",
            arguments={
                "message": "Here is the updated answer for the latest request.",
                "client_request_id": "tool-send-multi-1",
            },
            call_id="call-send-multi-1",
        )
    )
    llm_proxy.enqueue(_fixtures._text_response("Done with the second turn."))
