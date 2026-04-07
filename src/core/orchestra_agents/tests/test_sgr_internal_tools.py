from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agents.sgr.agent_runtime import event_loop as _event_loop
from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from agents.sgr.agent_runtime.internal_tools import execute_internal_tool
from agents.sgr.agent_runtime.support.outcomes import ParsedToolCall
from core.orchestra_agents.runtime import EventDelivery
from core.orchestra_agents.tests import test_sgr_example as _fixtures
from core.orchestra_thread import active_context as active_context_module


class SGRInternalToolsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "ORCHESTRA_THREADS_URL": os.environ.get("ORCHESTRA_THREADS_URL"),
            "LLM_PROXY_URL": os.environ.get("LLM_PROXY_URL"),
            "LLM_PROXY_ENABLED": os.environ.get("LLM_PROXY_ENABLED"),
            "LLM_PROXY_API_KEY": os.environ.get("LLM_PROXY_API_KEY"),
        }
        self.context_path = (
            Path(tempfile.mkdtemp(prefix="sgr_internal_tools_ctx_")) / "active_context.json"
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

    async def test_reasoning_tool_stores_context_memory(self) -> None:
        outcome = await execute_internal_tool(
            self.backend,
            ParsedToolCall(
                tool_name="reasoning_tool",
                arguments={
                    "reasoning_steps": ["Check recent thread state", "Decide next step"],
                    "current_situation": "The peer asked for an update",
                    "plan_status": "Need one concise answer",
                    "enough_data": True,
                    "remaining_steps": ["Send final answer"],
                    "task_completed": False,
                },
            ),
        )

        entries = self.backend._context_memory.recent_entries(None)
        self.assertEqual(outcome.tool_name, "reasoning_tool")
        self.assertTrue(entries)
        self.assertEqual(entries[-1].entry_type, "reasoning")

    async def test_clarification_tool_sends_message(self) -> None:
        active_context_module.write_active_context(
            {
                "agent_slug": "sgr",
                "thread_id": "thread-1",
                "root_thread_id": "thread-1",
                "parent_thread_id": None,
                "source_agent_slug": "secretary",
                "target_agent_slug": "sgr",
                "owner_agent_slug": "secretary",
                "current_mode": "reply",
            }
        )
        outcome = await execute_internal_tool(
            self.backend,
            ParsedToolCall(
                tool_name="clarification_tool",
                arguments={
                    "reasoning": "Need clarification before continuing",
                    "unclear_terms": ["deadline"],
                    "assumptions": ["Could mean today", "Could mean end of week"],
                    "questions": ["What deadline should I follow?"],
                },
            ),
        )
        active_context_module.clear_active_context()

        self.assertTrue(outcome.emitted_message)
        self.assertEqual(len(self.thread_service.message_calls), 1)
        self.assertIn(
            "What deadline should I follow?", self.thread_service.message_calls[0]["message_text"]
        )

    async def test_final_answer_tool_sends_message(self) -> None:
        active_context_module.write_active_context(
            {
                "agent_slug": "sgr",
                "thread_id": "thread-1",
                "root_thread_id": "thread-1",
                "parent_thread_id": None,
                "source_agent_slug": "secretary",
                "target_agent_slug": "sgr",
                "owner_agent_slug": "secretary",
                "current_mode": "reply",
            }
        )
        outcome = await execute_internal_tool(
            self.backend,
            ParsedToolCall(
                tool_name="final_answer_tool",
                arguments={
                    "reasoning": "The request is fully answered",
                    "completed_steps": ["Reviewed context", "Prepared answer"],
                    "answer": "Here is the final answer.",
                    "status": "completed",
                },
            ),
        )
        active_context_module.clear_active_context()

        self.assertTrue(outcome.emitted_message)
        self.assertEqual(len(self.thread_service.message_calls), 1)
        self.assertEqual(
            self.thread_service.message_calls[0]["message_text"],
            "Here is the final answer.",
        )

    async def test_context_memory_is_injected_into_messages(self) -> None:
        self.backend._context_memory.add_entry(
            thread_id="thread-1",
            entry_type="reasoning",
            text="Need to provide the final answer",
            metadata_summary="ready",
        )
        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-memory",
                "events": [
                    {
                        "event_id": "event-memory",
                        "thread_id": "thread-1",
                        "root_thread_id": "thread-1",
                        "parent_thread_id": None,
                        "owner_agent_slug": "secretary",
                        "sequence_no": 20,
                        "event_kind": "message",
                        "notification_status": None,
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Please send the final answer.",
                        "interrupts_runtime": True,
                        "requires_response": True,
                    }
                ],
            }
        )

        messages = _event_loop._build_messages(
            self.backend,
            self.thread_service.compact_threads["thread-1"],
            "secretary",
            delivery,
            delivery.events[0],
        )

        system_messages = [
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "system"
        ]
        self.assertTrue(any("Recent context:" in item for item in system_messages))


if __name__ == "__main__":
    unittest.main()
