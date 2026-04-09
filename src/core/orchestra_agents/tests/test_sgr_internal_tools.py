from __future__ import annotations

import os
import tempfile
import unittest

from core.orchestra_agents.backends.sgr import SGRMinimaxBackend
from core.orchestra_agents.backends.sgr import event_loop as _event_loop
from core.orchestra_agents.backends.sgr.internal_tools import execute_internal_tool
from core.orchestra_agents.backends.sgr.support.outcomes import ParsedToolCall
from core.orchestra_agents.runtime import EventDelivery
from core.orchestra_agents.tests.template_helpers.sgr_fake_omniroute import FakeOmniRoute

_LONG_REASONING_LENGTH = 2100


class SGRInternalToolsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "OMNIROUTE_URL": os.environ.get("OMNIROUTE_URL"),
            "OMNIROUTE_API_KEY": os.environ.get("OMNIROUTE_API_KEY"),
        }
        self.omniroute = FakeOmniRoute()
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
            system_prompt="Use available MCP tools.",
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

    async def test_reasoning_tool_returns_structured_result(self) -> None:
        outcome = execute_internal_tool(
            self.backend,
            ParsedToolCall(
                tool_name="reasoning_tool",
                arguments={
                    "reasoning_steps": ["Check state", "Decide next step"],
                    "current_situation": "The peer asked for an update",
                    "plan_status": "Need one concise answer",
                    "enough_data": True,
                    "remaining_steps": ["Send final answer"],
                    "task_completed": False,
                },
            ),
        )

        self.assertEqual(outcome.tool_name, "reasoning_tool")
        self.assertIn("Check state", outcome.result_text)

    async def test_clarification_tool_structured(self) -> None:
        outcome = execute_internal_tool(
            self.backend,
            ParsedToolCall(
                tool_name="clarification_tool",
                arguments={
                    "reasoning": "Need clarification",
                    "unclear_terms": ["deadline"],
                    "assumptions": ["Could mean today", "Could mean end of week"],
                    "questions": ["What deadline should I follow?"],
                },
            ),
        )

        self.assertFalse(outcome.emitted_message)
        self.assertIn("deadline", outcome.result_text)

    async def test_final_answer_tool_structured(self) -> None:
        outcome = execute_internal_tool(
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

        self.assertFalse(outcome.emitted_message)
        self.assertIn("final answer", outcome.result_text)

    async def test_chat_history_injected_into_messages(self) -> None:
        self.backend._chat_history.record_turn(
            session_key="default",
            user_text="Need to provide the final answer",
            assistant_text="ready",
        )
        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-memory",
                "events": [
                    {
                        "event_id": "event-memory",
                        "thread_id": None,
                        "root_thread_id": None,
                        "parent_thread_id": None,
                        "owner_agent_slug": None,
                        "sequence_no": 20,
                        "event_kind": "message",
                        "notification_status": None,
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Please send the final answer.",
                        "interrupts_runtime": True,
                        "requires_response": True,
                    },
                ],
            },
        )

        messages = _event_loop._build_messages(
            self.backend,
            "default",
            "secretary",
            delivery,
            delivery.events[0],
        )

        [
            str(msg.get("content") or "")
            for msg in messages
            if isinstance(msg, dict) and msg.get("role") == "system"
        ]
        assistant_messages = [
            str(msg.get("content") or "")
            for msg in messages
            if isinstance(msg, dict) and msg.get("role") == "assistant"
        ]
        self.assertIn("ready", assistant_messages)

    async def test_clarification_tool_truncates_reasoning(self) -> None:
        outcome = execute_internal_tool(
            self.backend,
            ParsedToolCall(
                tool_name="clarification_tool",
                arguments={
                    "reasoning": "x" * _LONG_REASONING_LENGTH,
                    "unclear_terms": ["deadline"],
                    "assumptions": ["today", "tomorrow"],
                    "questions": ["Which deadline applies?"],
                },
            ),
        )
        self.assertIn("technical_context", outcome.result_text)


if __name__ == "__main__":
    unittest.main()
