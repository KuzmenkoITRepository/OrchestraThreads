from __future__ import annotations

import json
import os
import socket
import unittest
from typing import Any

from aiohttp import web

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from core.orchestra_agents.runtime import EventDelivery


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


def _stream_tool_response(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    call_id: str,
    model: str = "gpt-5.4-mini-2026-03-17",
) -> list[dict[str, Any]]:
    serialized_args = json.dumps(arguments, ensure_ascii=False)
    chunks = [serialized_args[index : index + 8] for index in range(0, len(serialized_args), 8)]
    result: list[dict[str, Any]] = [
        {
            "id": "chatcmpl-stream-tool",
            "object": "chat.completion.chunk",
            "created": 1735689600,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": call_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": ""},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
    ]
    for raw_chunk in chunks:
        result.append(
            {
                "id": "chatcmpl-stream-tool",
                "object": "chat.completion.chunk",
                "created": 1735689600,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [{"index": 0, "function": {"arguments": raw_chunk}}]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )
    result.append(
        {
            "id": "chatcmpl-stream-tool",
            "object": "chat.completion.chunk",
            "created": 1735689600,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        }
    )
    return result


def _base_event_payload() -> dict[str, Any]:
    return {
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


def _build_delivery(*, delivery_id: str, event_payload: dict[str, Any]) -> EventDelivery:
    return EventDelivery.from_dict(
        {
            "delivery_id": delivery_id,
            "events": [event_payload],
        }
    )


def _assert_message_event_result(
    test_case: unittest.IsolatedAsyncioTestCase,
    observed: dict[str, Any],
) -> None:
    test_case.assertEqual(
        observed,
        {
            "accepted": True,
            "chat_requests": 3,
            "model": "MiniMax-M2.7",
            "message": "Draft ready for handoff.",
            "sent": 1,
            "tool_calls": 2,
            "last_peer": "secretary",
            "last_reply": "Draft ready for handoff.",
            "last_action": True,
        },
    )


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


class FakeOmniRoute:
    def __init__(self) -> None:
        self.port = _free_port()
        self.runner: web.AppRunner | None = None
        self.chat_requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any] | list[dict[str, Any]]] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def enqueue(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.responses.append(payload)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/v1/chat/completions", self._handle_chat)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _handle_chat(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.chat_requests.append(
            {
                "path": request.path,
                "headers": dict(request.headers),
                "payload": payload,
                "request": request,
            }
        )
        if not self.responses:
            return web.json_response(
                {"error": {"message": "No queued fake LLM response"}}, status=500
            )
        queued_payload = self.responses.pop(0)
        if payload.get("stream"):
            return await self._handle_stream_response(queued_payload)
        if not isinstance(queued_payload, dict):
            return web.json_response(
                {"error": {"message": "Expected non-stream response payload"}}, status=500
            )
        response_payload = dict(queued_payload)
        response_payload["model"] = (
            payload.get("model") or response_payload.get("model") or "MiniMax-M2.7"
        )
        return web.json_response(response_payload)

    async def _handle_stream_response(
        self,
        response_payload: dict[str, Any] | list[dict[str, Any]],
    ) -> web.StreamResponse:
        stream = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        request = self.chat_requests[-1]["request"]
        await stream.prepare(request)
        chunks = response_payload if isinstance(response_payload, list) else [response_payload]
        await _write_stream_chunks(stream, chunks)
        await stream.write_eof()
        return stream


async def _write_stream_chunks(
    stream: web.StreamResponse,
    chunks: list[dict[str, Any]],
) -> None:
    lines = [f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks]
    lines.append("data: [DONE]\n\n")
    await stream.write("".join(lines).encode())


class _SGRMinimaxBackendBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_env = {
            "OMNIROUTE_URL": os.environ.get("OMNIROUTE_URL"),
            "OMNIROUTE_API_KEY": os.environ.get("OMNIROUTE_API_KEY"),
        }

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
        self.omniroute = FakeOmniRoute()
        await self.thread_service.start()
        await self.omniroute.start()
        os.environ["OMNIROUTE_URL"] = self.omniroute.base_url
        os.environ["OMNIROUTE_API_KEY"] = "omniroute-test-key"
        self.backend = SGRMinimaxBackend(
            agent_slug="sgr",
            backend_type="sgr_minimax",
            working_dir="/workspace/agents/sgr",
            config={
                "route_policy": "minimax_only",
                "model": "MiniMax-M2.7",
                "react_to_inactive": True,
                "max_reasoning_steps": 6,
                "max_direct_text_retries": 1,
            },
            system_prompt="Use thread_send or thread_status via OrchestraThreads MCP tools.",
        )
        self._fake_mcp = _FakeToolMCPServer(self.thread_service)
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
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
        result = await self.backend.handle_events(delivery)
        first_payload = self.omniroute.chat_requests[0]["payload"]
        status = await self.backend.last_status()
        observed = {
            "accepted": result.accepted,
            "chat_requests": len(self.omniroute.chat_requests),
            "model": first_payload["model"],
            "message": self.thread_service.message_calls[0]["message"],
            "sent": result.details["messages_sent"],
            "tool_calls": result.details["tool_calls"],
            "last_peer": status["last_peer_agent_slug"],
            "last_reply": status["last_reply_preview"],
            "last_action": status["last_action_emitted"],
        }
        _assert_message_event_result(self, observed)
        first_headers = self.omniroute.chat_requests[0]["headers"]
        self.assertEqual(self.omniroute.chat_requests[0]["path"], "/v1/chat/completions")
        self.assertTrue(first_payload["tools"])
        self.assertEqual(
            first_headers.get("Authorization"),
            "Bearer omniroute-test-key",
        )
        self.assertIn("thread_send", result.details["used_tools"])

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
        result = await self.backend.handle_events(delivery)

        self.assertEqual(
            (
                result.accepted,
                len(self.thread_service.message_calls),
                len(self.omniroute.chat_requests),
            ),
            (True, 1, 3),
        )
        second_payload = self.omniroute.chat_requests[1]["payload"]
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

        result = await self.backend.handle_events(delivery)

        _assert_inactive_delivery_result(self, result, self.thread_service.notification_calls)

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
        self.assertEqual(len(self.omniroute.chat_requests), 2)


class _FakeToolMCPServer:
    """Fake MCP server that delegates tool calls to a FakeThreadService."""

    def __init__(self, thread_service: FakeThreadService) -> None:
        self._thread_service = thread_service

    async def handle_tools_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Route tool calls to the fake thread service."""
        if name == "thread_send":
            msg = str(arguments.get("message") or "")
            self._thread_service.message_calls.append(arguments)
            return _fake_mcp_result({"ok": True, "message": msg, "route": "auto"})
        if name == "thread_status":
            self._thread_service.notification_calls.append(arguments)
            status = str(arguments.get("status") or "")
            return _fake_mcp_result({"ok": True, "published_status": status})
        return _fake_mcp_result({"ok": True})

    async def close(self) -> None:
        """No-op close."""


def _fake_mcp_result(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(structured)}],
        "structuredContent": structured,
    }


def _inactive_status_tool_response() -> dict[str, Any]:
    return _tool_response(
        tool_name="thread_status",
        arguments={
            "status": "in_progress",
            "message": "Still working on the requested summary.",
            "client_request_id": "tool-status-1",
        },
        call_id="call-status",
    )


def _assert_inactive_delivery_result(
    test_case: unittest.IsolatedAsyncioTestCase,
    result: Any,
    notification_calls: list[dict[str, Any]],
) -> None:
    test_case.assertTrue(result.accepted)
    test_case.assertEqual(len(notification_calls), 1)
    test_case.assertEqual(notification_calls[0]["status"], "in_progress")
    test_case.assertEqual(result.details["statuses_published"], 1)
    test_case.assertEqual(result.details["published_status"], "in_progress")


if __name__ == "__main__":
    unittest.main()
