from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aiohttp import web

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from core.orchestra_agents.runtime import EventDelivery
from core.orchestra_thread import active_context as active_context_module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _tool_response(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    call_id: str,
    model: str = "MiniMax-M2.7",
) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{call_id}",
        "object": "chat.completion",
        "created": 1735689600,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _text_response(text: str, *, model: str = "MiniMax-M2.7") -> dict[str, Any]:
    return {
        "id": "chatcmpl-text",
        "object": "chat.completion",
        "created": 1735689600,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _assert_message_event_result(
    test_case: unittest.IsolatedAsyncioTestCase,
    *,
    result: Any,
    status: dict[str, Any],
    observed: dict[str, Any],
) -> None:
    test_case.assertEqual(
        observed,
        {
            "accepted": True,
            "register_calls": 1,
            "chat_requests": 3,
            "model": "MiniMax-M2.7",
            "to_agent": "secretary",
            "thread": "thread-1",
            "request_id": "tool-reply-1",
            "message": "Draft ready for handoff.",
            "sent": 1,
            "tool_calls": 2,
            "last_thread": "thread-1",
            "last_peer": "secretary",
            "last_reply": "Draft ready for handoff.",
            "last_action": True,
        },
    )
    test_case.assertIn("thread_send", result.details["used_tools"])


class FakeThreadService:
    def __init__(self) -> None:
        self._port = _free_port()
        self.runner: web.AppRunner | None = None
        self.register_calls: list[dict[str, Any]] = []
        self.heartbeat_calls: list[dict[str, Any]] = []
        self.message_calls: list[dict[str, Any]] = []
        self.notification_calls: list[dict[str, Any]] = []
        self.compact_threads: dict[str, dict[str, Any]] = {}

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/agents/register", self._handle_post)
        app.router.add_post("/agents/heartbeat", self._handle_post)
        app.router.add_post("/api/v1/messages", self._handle_post)
        app.router.add_post("/api/v1/notifications", self._handle_post)
        app.router.add_get("/api/v1/instructions", self._handle_instructions)
        app.router.add_get("/api/v1/threads/{thread_id}/compact", self._handle_threads)
        app.router.add_get("/api/v1/threads/{thread_id}", self._handle_threads)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self._port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _handle_post(self, request: web.Request) -> web.Response:
        payload = await request.json()
        if request.path == "/agents/register":
            self.register_calls.append(payload)
            return web.json_response(
                {
                    "success": True,
                    "agent": {
                        "agent_slug": payload.get("agent_slug"),
                        "base_url": payload.get("base_url"),
                    },
                    "agent_lease_seconds": 30,
                }
            )
        if request.path == "/agents/heartbeat":
            self.heartbeat_calls.append(payload)
            return web.json_response(
                {
                    "success": True,
                    "agent": {
                        "agent_slug": payload.get("agent_slug"),
                    },
                }
            )
        if request.path == "/api/v1/messages":
            self.message_calls.append(payload)
            return web.json_response(
                {
                    "success": True,
                    "operation": "message",
                    "created_thread": False,
                    "thread": {"thread_id": payload.get("thread_id"), "status": "open"},
                    "event": {"event_id": "reply-event-1"},
                }
            )
        self.notification_calls.append(payload)
        return web.json_response(
            {
                "success": True,
                "operation": "notification",
                "thread": {
                    "thread_id": payload.get("thread_id"),
                    "status": payload.get("status") or "open",
                },
                "event": {"event_id": "notification-event-1"},
            }
        )

    async def _handle_instructions(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "success": True,
                "instruction": {
                    "text": (
                        "OrchestraThreads guide\n"
                        "Use thread_current first when state is unclear.\n"
                        "Use thread_send for replies and thread_status for lifecycle updates."
                    ),
                    "view": request.query.get("view", "compact"),
                    "section": request.query.get("section", "all"),
                },
            }
        )

    async def _handle_threads(self, request: web.Request) -> web.Response:
        thread_id = request.match_info["thread_id"]
        if request.path.endswith("/compact"):
            return web.json_response(
                {
                    "success": True,
                    "thread": self.compact_threads[thread_id],
                }
            )
        return web.json_response(
            {
                "success": True,
                "thread": self.compact_threads[thread_id],
                "events": [],
                "related": {},
            }
        )


class FakeLLMProxy:
    def __init__(self) -> None:
        self.port = _free_port()
        self.runner: web.AppRunner | None = None
        self.chat_requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def enqueue(self, payload: dict[str, Any]) -> None:
        self.responses.append(payload)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/minimax/v1/chat/completions", self._handle_chat)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _handle_chat(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.chat_requests.append(
            {
                "path": request.path,
                "headers": dict(request.headers),
                "payload": payload,
            }
        )
        if not self.responses:
            return web.json_response(
                {"error": {"message": "No queued fake LLM response"}}, status=500
            )
        response_payload = dict(self.responses.pop(0))
        response_payload["model"] = (
            payload.get("model") or response_payload.get("model") or "MiniMax-M2.7"
        )
        return web.json_response(response_payload)


class SGRMinimaxBackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "ORCHESTRA_THREADS_URL": os.environ.get("ORCHESTRA_THREADS_URL"),
            "LLM_PROXY_URL": os.environ.get("LLM_PROXY_URL"),
            "LLM_PROXY_ENABLED": os.environ.get("LLM_PROXY_ENABLED"),
            "LLM_PROXY_API_KEY": os.environ.get("LLM_PROXY_API_KEY"),
        }
        self.context_path = (
            Path(tempfile.mkdtemp(prefix="sgr_runtime_ctx_")) / "active_context.json"
        )
        self.original_context_path = active_context_module.ACTIVE_CONTEXT_PATH
        active_context_module.ACTIVE_CONTEXT_PATH = self.context_path

        self.thread_service = FakeThreadService()
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
        self.llm_proxy = FakeLLMProxy()
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

    async def test_message_event_triggers_mcp_tools(self) -> None:
        self.llm_proxy.enqueue(
            _tool_response(tool_name="thread_current", arguments={}, call_id="call-current")
        )
        self.llm_proxy.enqueue(
            _tool_response(
                tool_name="thread_send",
                arguments={
                    "message": "Draft ready for handoff.",
                    "client_request_id": "tool-reply-1",
                },
                call_id="call-send",
            )
        )
        self.llm_proxy.enqueue(_text_response("Turn complete."))

        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-1",
                "events": [
                    {
                        "event_id": "event-1",
                        "thread_id": "thread-1",
                        "root_thread_id": "thread-1",
                        "parent_thread_id": None,
                        "owner_agent_slug": "secretary",
                        "sequence_no": 3,
                        "event_kind": "message",
                        "notification_status": None,
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Please prepare the summary.",
                        "interrupts_runtime": True,
                        "requires_response": True,
                        "created_at": "2026-04-03T07:00:00Z",
                    }
                ],
            }
        )
        result = await self.backend.handle_events(delivery)
        first_payload = self.llm_proxy.chat_requests[0]["payload"]
        self.assertEqual(self.llm_proxy.chat_requests[0]["path"], "/minimax/v1/chat/completions")
        status = await self.backend.last_status()
        observed = {
            "accepted": result.accepted,
            "register_calls": len(self.thread_service.register_calls),
            "chat_requests": len(self.llm_proxy.chat_requests),
            "model": first_payload["model"],
            "to_agent": self.thread_service.message_calls[0]["to_agent_slug"],
            "thread": self.thread_service.message_calls[0]["thread_id"],
            "request_id": self.thread_service.message_calls[0]["client_request_id"],
            "message": self.thread_service.message_calls[0]["message_text"],
            "sent": result.details["messages_sent"],
            "tool_calls": result.details["tool_calls"],
            "last_thread": status["last_thread_id"],
            "last_peer": status["last_peer_agent_slug"],
            "last_reply": status["last_reply_preview"],
            "last_action": status["last_action_emitted"],
        }
        _assert_message_event_result(
            self,
            result=result,
            status=status,
            observed=observed,
        )
        self.assertTrue(first_payload["tools"])
        self.assertIn("thread_send", result.details["used_tools"])

    async def test_direct_text_ignored_before_tool(self) -> None:
        self.llm_proxy.enqueue(_text_response("I would answer with a short summary."))
        self.llm_proxy.enqueue(
            _tool_response(
                tool_name="thread_send",
                arguments={
                    "message": "Here is the requested short summary.",
                    "client_request_id": "tool-reply-2",
                },
                call_id="call-send",
            )
        )
        self.llm_proxy.enqueue(_text_response("Done."))

        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-1",
                "events": [
                    {
                        "event_id": "event-1",
                        "thread_id": "thread-1",
                        "root_thread_id": "thread-1",
                        "parent_thread_id": None,
                        "owner_agent_slug": "secretary",
                        "sequence_no": 3,
                        "event_kind": "message",
                        "notification_status": None,
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Please prepare the summary.",
                        "interrupts_runtime": True,
                        "requires_response": True,
                        "created_at": "2026-04-03T07:00:00Z",
                    }
                ],
            }
        )
        result = await self.backend.handle_events(delivery)

        self.assertEqual(
            (
                result.accepted,
                len(self.thread_service.message_calls),
                len(self.llm_proxy.chat_requests),
            ),
            (True, 1, 3),
        )
        second_payload = self.llm_proxy.chat_requests[1]["payload"]
        reminder_messages = [
            str(message.get("content") or "")
            for message in second_payload["messages"]
            if isinstance(message, dict) and message.get("role") == "system"
        ]
        self.assertTrue(
            any("Direct assistant text helps you think" in item for item in reminder_messages)
        )
        self.assertTrue(result.details["direct_text_ignored"])

        status = await self.backend.last_status()
        self.assertEqual(
            (status["last_reply_preview"], status["last_ignored_output_preview"]),
            ("Here is the requested short summary.", "Done."),
        )

    async def test_inactive_event_publishes_status(self) -> None:
        self.llm_proxy.enqueue(
            _tool_response(
                tool_name="thread_status",
                arguments={
                    "status": "in_progress",
                    "message": "Still working on the requested summary.",
                    "client_request_id": "tool-status-1",
                },
                call_id="call-status",
            )
        )
        self.llm_proxy.enqueue(_text_response("Done."))

        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-2",
                "events": [
                    {
                        "event_id": "event-2",
                        "thread_id": "thread-1",
                        "root_thread_id": "thread-1",
                        "parent_thread_id": None,
                        "owner_agent_slug": "secretary",
                        "sequence_no": 4,
                        "event_kind": "inactive",
                        "notification_status": None,
                        "from_agent_slug": "orchestra_threads",
                        "to_agent_slug": "sgr",
                        "message_text": "",
                        "interrupts_runtime": True,
                        "requires_response": False,
                        "created_at": "2026-04-03T07:01:00Z",
                    }
                ],
            }
        )

        result = await self.backend.handle_events(delivery)

        self.assertTrue(result.accepted)
        self.assertEqual(len(self.thread_service.notification_calls), 1)
        self.assertEqual(self.thread_service.notification_calls[0]["status"], "in_progress")
        self.assertEqual(result.details["statuses_published"], 1)
        self.assertEqual(result.details["published_status"], "in_progress")

        status = await self.backend.last_status()
        self.assertEqual(status["last_published_status"], "in_progress")
        self.assertEqual(status["last_status_preview"], "Still working on the requested summary.")

    async def test_duplicate_delivery_skips_tool(self) -> None:
        self.llm_proxy.enqueue(
            _tool_response(tool_name="thread_current", arguments={}, call_id="call-current")
        )
        self.llm_proxy.enqueue(
            _tool_response(
                tool_name="thread_send",
                arguments={
                    "message": "Draft ready for handoff.",
                    "client_request_id": "tool-reply-3",
                },
                call_id="call-send",
            )
        )
        self.llm_proxy.enqueue(_text_response("Turn complete."))

        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-1",
                "events": [
                    {
                        "event_id": "event-1",
                        "thread_id": "thread-1",
                        "root_thread_id": "thread-1",
                        "parent_thread_id": None,
                        "owner_agent_slug": "secretary",
                        "sequence_no": 3,
                        "event_kind": "message",
                        "notification_status": None,
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Please prepare the summary.",
                        "interrupts_runtime": True,
                        "requires_response": True,
                        "created_at": "2026-04-03T07:00:00Z",
                    }
                ],
            }
        )
        first = await self.backend.handle_events(delivery)
        second = await self.backend.handle_events(delivery)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertTrue(second.duplicate)
        self.assertEqual(len(self.thread_service.message_calls), 1)
        self.assertEqual(len(self.llm_proxy.chat_requests), 3)

    async def test_notification_event_processed(self) -> None:
        self.llm_proxy.enqueue(_text_response("Noted. I will keep that in mind."))
        self.llm_proxy.enqueue(_text_response("Nothing else to send right now."))
        delivery = EventDelivery.from_dict(
            {
                "delivery_id": "delivery-3",
                "events": [
                    {
                        "event_id": "event-3",
                        "thread_id": "thread-1",
                        "event_kind": "notification",
                        "notification_status": "review",
                        "from_agent_slug": "secretary",
                        "to_agent_slug": "sgr",
                        "message_text": "Review is ready.",
                        "interrupts_runtime": True,
                        "requires_response": False,
                    }
                ],
            }
        )

        result = await self.backend.handle_events(delivery)

        self.assertTrue(result.accepted)
        self.assertEqual(result.details["reason"], "no_tool_action_emitted")
        self.assertNotIn("event_metadata", result.details)
        self.assertEqual(len(self.thread_service.message_calls), 0)
        self.assertEqual(len(self.thread_service.notification_calls), 0)
        self.assertEqual(len(self.llm_proxy.chat_requests), 2)


if __name__ == "__main__":
    unittest.main()
