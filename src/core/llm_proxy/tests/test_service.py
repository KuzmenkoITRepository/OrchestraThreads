from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from core.llm_proxy.langfuse import build_group_key
from core.llm_proxy.service import LLMProxyService, ProxyConfig, build_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class FakeUpstream:
    def __init__(self) -> None:
        self.port = _free_port()
        self.runner: web.AppRunner | None = None
        self.codex_behaviors: dict[str, dict[str, Any]] = {}
        self.fallback_behavior: dict[str, Any] = {"status": 200, "content": "fallback ok"}
        self.codex_requests: list[dict[str, Any]] = []
        self.fallback_requests: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/healthz", self._handle_healthz)
        app.router.add_post("/backend-api/codex/responses", self._handle_codex)
        app.router.add_post("/v1/chat/completions", self._handle_fallback)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    def reset(self) -> None:
        self.codex_behaviors = {}
        self.fallback_behavior = {"status": 200, "content": "fallback ok"}
        self.codex_requests = []
        self.fallback_requests = []

    def set_codex_behavior(
        self,
        account_id: str,
        *,
        status: int = 200,
        content: str = "codex ok",
        error: str = "upstream error",
    ) -> None:
        self.codex_behaviors[account_id] = {
            "status": status,
            "content": content,
            "error": error,
        }

    def set_fallback_behavior(
        self,
        *,
        status: int = 200,
        content: str = "fallback ok",
        error: str = "fallback error",
    ) -> None:
        self.fallback_behavior = {
            "status": status,
            "content": content,
            "error": error,
        }

    async def _handle_healthz(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_codex(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        account_id = str(request.headers.get("chatgpt-account-id") or "")
        self.codex_requests.append({"account_id": account_id, "payload": payload})
        behavior = self.codex_behaviors.get(
            account_id, {"status": 200, "content": "codex ok", "error": "error"}
        )
        if int(behavior["status"]) >= 400:
            return web.json_response(
                {"error": {"message": behavior["error"]}},
                status=int(behavior["status"]),
            )
        text = str(behavior["content"])
        response = web.StreamResponse(
            status=200, headers={"Content-Type": "text/event-stream; charset=utf-8"}
        )
        await response.prepare(request)
        events = [
            {
                "type": "response.output_item.added",
                "item": {"type": "message", "id": "msg_1"},
            },
            {
                "type": "response.output_text.delta",
                "delta": text,
            },
            {
                "type": "response.output_item.done",
                "item": {"type": "message", "content": [{"type": "output_text", "text": text}]},
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                },
            },
        ]
        for event in events:
            await response.write(f"data: {json.dumps(event)}\n\n".encode())
        await response.write(b"data: [DONE]\n\n")
        await response.write_eof()
        return response

    async def _handle_fallback(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.fallback_requests.append(payload)
        if int(self.fallback_behavior["status"]) >= 400:
            return web.json_response(
                {"error": {"message": self.fallback_behavior["error"]}},
                status=int(self.fallback_behavior["status"]),
            )
        return web.json_response(
            {
                "id": "chatcmpl-fallback",
                "object": "chat.completion",
                "created": 1735689600,
                "model": payload.get("model") or "minimax-text-01",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": self.fallback_behavior["content"],
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            }
        )


class FakeGenerationContext:
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record

    def __enter__(self) -> FakeGenerationContext:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def update(self, **kwargs: Any) -> None:
        self.record.setdefault("updates", []).append(kwargs)


class FakeRequestTrace:
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record

    def __enter__(self) -> FakeRequestTrace:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input_payload: Any = None,
        metadata: dict[str, Any] | None = None,
        model_parameters_payload: dict[str, Any] | None = None,
    ) -> FakeGenerationContext:
        generation = {
            "name": name,
            "model": model,
            "input_payload": input_payload,
            "metadata": metadata or {},
            "model_parameters": model_parameters_payload or {},
            "updates": [],
        }
        self.record.setdefault("generations", []).append(generation)
        return FakeGenerationContext(generation)

    def mark_success(self, *, output: Any = None, metadata: dict[str, Any] | None = None) -> None:
        self.record["success"] = {"output": output, "metadata": metadata or {}}

    def mark_error(
        self, *, error: Exception | str, output: Any = None, metadata: dict[str, Any] | None = None
    ) -> None:
        self.record["error"] = {"message": str(error), "output": output, "metadata": metadata or {}}


class FakeTelemetry:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.shutdown_calls = 0

    @property
    def enabled(self) -> bool:
        return True

    def start_request(
        self,
        *,
        request_kind: str,
        agent_slug: str | None,
        context_id: str | None,
        metadata: dict[str, Any] | None,
        input_payload: Any,
        tags: list[str] | None = None,
    ) -> FakeRequestTrace:
        record = {
            "request_kind": request_kind,
            "agent_slug": agent_slug,
            "context_id": context_id,
            "group_key": build_group_key(agent_slug, context_id),
            "metadata": metadata or {},
            "input_payload": input_payload,
            "tags": tags or [],
            "generations": [],
        }
        self.requests.append(record)
        return FakeRequestTrace(record)

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class LLMProxyServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.auth_profiles_path = Path(self.tmpdir.name) / "auth-profiles.json"
        self.rotation_state_path = Path(self.tmpdir.name) / "proxy-state.json"
        self.auth_profiles_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "profiles": {
                        "primary": {
                            "type": "oauth",
                            "provider": "openai-codex",
                            "access": "access-primary",
                            "refresh": "refresh-primary",
                            "expires": 4102444800000,
                            "accountId": "acct-primary",
                        },
                        "secondary": {
                            "type": "oauth",
                            "provider": "openai-codex",
                            "access": "access-secondary",
                            "refresh": "refresh-secondary",
                            "expires": 4102444800000,
                            "accountId": "acct-secondary",
                        },
                    },
                    "order": {"openai-codex": ["primary", "secondary"]},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.upstream = FakeUpstream()
        await self.upstream.start()
        self.telemetry = FakeTelemetry()
        self.service = LLMProxyService(
            ProxyConfig(
                host="127.0.0.1",
                port=_free_port(),
                model="gpt-5.4",
                base_url=f"{self.upstream.base_url}/backend-api",
                auth_profiles_path=self.auth_profiles_path,
                profile_id="primary",
                profile_ids=("primary", "secondary"),
                default_system_instructions="You are a helpful assistant.",
                text_verbosity="medium",
                reasoning_effort=None,
                reasoning_summary="auto",
                temperature=None,
                request_timeout_seconds=10,
                account_failure_cooldown_seconds=120,
                rotation_state_path=self.rotation_state_path,
                fallback_base_url=f"{self.upstream.base_url}/v1",
                fallback_api_key="fallback-key",
                fallback_model="minimax-text-01",
                fallback_timeout_seconds=10,
                langfuse_enabled=True,
            ),
            telemetry=self.telemetry,
        )
        self.runner = web.AppRunner(build_app(self.service))
        await self.runner.setup()
        self.port = _free_port()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.runner.cleanup()
        await self.upstream.stop()
        self.tmpdir.cleanup()

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        async with self.session.request(
            method,
            f"http://127.0.0.1:{self.port}{path}",
            json=payload,
            headers=headers,
        ) as response:
            raw = await response.text()
            data = json.loads(raw) if raw else {}
            if response.status != expected_status:
                raise AssertionError(f"{method} {path} -> {response.status}: {data}")
            return data

    async def test_managed_auto_rotates_to_second_codex_account(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", status=429, error="usage limit reached")
        self.upstream.set_codex_behavior("acct-secondary", content="secondary reply")
        payload = {
            "instructions": "You are a helper.",
            "input_items": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
            "tools": None,
        }
        result = await self._request("POST", "/v1/codex/responses", payload)
        self.assertEqual(result["items"][0]["type"], "assistant_text")
        self.assertEqual(result["items"][0]["text"], "secondary reply")
        self.assertEqual(
            [item["account_id"] for item in self.upstream.codex_requests],
            ["acct-primary", "acct-secondary"],
        )
        accounts = await self._request("GET", "/accounts/status")
        profiles = {item["profile_id"]: item for item in accounts["profiles"]}
        self.assertEqual(profiles["primary"]["failure_count"], 1)
        self.assertTrue(profiles["primary"]["cooldown_active"])
        self.assertEqual(profiles["secondary"]["success_count"], 1)

    async def test_responses_alias_routes_to_managed_auto_codex_path(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", content="alias reply")
        payload = {
            "instructions": "You are a helper.",
            "input_items": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
            "tools": None,
        }
        result = await self._request("POST", "/v1/responses", payload)
        self.assertEqual(result["items"][0]["text"], "alias reply")
        self.assertEqual(len(self.upstream.codex_requests), 1)
        self.assertEqual(self.upstream.codex_requests[0]["account_id"], "acct-primary")

    async def test_responses_alias_accepts_standard_input_field(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", content="alias reply")
        payload = {
            "instructions": "You are a helper.",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
            "tools": None,
        }
        result = await self._request("POST", "/v1/responses", payload)
        self.assertEqual(result["items"][0]["text"], "alias reply")
        self.assertEqual(len(self.upstream.codex_requests), 1)
        self.assertEqual(self.upstream.codex_requests[0]["account_id"], "acct-primary")

    async def test_responses_alias_streams_sse_events(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", content="stream reply")
        async with self.session.post(
            f"http://127.0.0.1:{self.port}/v1/responses",
            json={
                "instructions": "You are a helper.",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
                "tools": None,
                "stream": True,
            },
        ) as response:
            body = await response.text()
        self.assertEqual(response.status, 200)
        self.assertIn("response.output_text.delta", body)
        self.assertIn("stream reply", body)
        self.assertIn("response.completed", body)
        self.assertIn("[DONE]", body)

    async def test_managed_auto_falls_back_to_minimax_when_all_codex_accounts_fail(self) -> None:
        self.upstream.set_codex_behavior(
            "acct-primary", status=503, error="temporarily unavailable"
        )
        self.upstream.set_codex_behavior(
            "acct-secondary", status=503, error="temporarily unavailable"
        )
        self.upstream.set_fallback_behavior(content="fallback reply")
        result = await self._request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(result["choices"][0]["message"]["content"], "fallback reply")
        self.assertEqual(len(self.upstream.codex_requests), 2)
        self.assertEqual(len(self.upstream.fallback_requests), 1)
        health = await self._request("GET", "/healthz")
        self.assertEqual(health["status"], "ok")

    async def test_minimax_only_codex_route_skips_codex_accounts(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", status=500, error="should not be called")
        self.upstream.set_codex_behavior("acct-secondary", status=500, error="should not be called")
        self.upstream.set_fallback_behavior(content="direct minimax")
        result = await self._request(
            "POST",
            "/minimax/v1/codex/responses",
            {
                "instructions": "You are a helper.",
                "input_items": [
                    {"role": "user", "content": [{"type": "input_text", "text": "ping"}]}
                ],
                "tools": None,
            },
        )
        self.assertEqual(result["items"][0]["text"], "direct minimax")
        self.assertEqual(len(self.upstream.codex_requests), 0)
        self.assertEqual(len(self.upstream.fallback_requests), 1)

    async def test_codex_only_responses_alias_skips_fallback(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", content="codex alias")
        result = await self._request(
            "POST",
            "/codex/v1/responses",
            {
                "instructions": "You are a helper.",
                "input_items": [
                    {"role": "user", "content": [{"type": "input_text", "text": "ping"}]}
                ],
                "tools": None,
            },
        )
        self.assertEqual(result["items"][0]["text"], "codex alias")
        self.assertEqual(len(self.upstream.codex_requests), 1)
        self.assertEqual(len(self.upstream.fallback_requests), 0)

    async def test_minimax_only_chat_route_uses_requested_model(self) -> None:
        self.upstream.set_fallback_behavior(content="direct minimax chat")
        result = await self._request(
            "POST",
            "/minimax/v1/chat/completions",
            {
                "model": "MiniMax-M2.7",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(result["choices"][0]["message"]["content"], "direct minimax chat")
        self.assertEqual(result["model"], "MiniMax-M2.7")
        self.assertEqual(len(self.upstream.codex_requests), 0)
        self.assertEqual(len(self.upstream.fallback_requests), 1)
        self.assertEqual(self.upstream.fallback_requests[0]["model"], "MiniMax-M2.7")

    async def test_codex_only_returns_503_without_fallback(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", status=429, error="usage limit reached")
        self.upstream.set_codex_behavior("acct-secondary", status=429, error="usage limit reached")
        self.upstream.set_fallback_behavior(content="should stay unused")
        result = await self._request(
            "POST",
            "/codex/v1/codex/responses",
            {
                "instructions": "You are a helper.",
                "input_items": [
                    {"role": "user", "content": [{"type": "input_text", "text": "ping"}]}
                ],
                "tools": None,
            },
            expected_status=503,
        )
        self.assertIn("primary", result["error"]["message"])
        self.assertEqual(len(self.upstream.fallback_requests), 0)

    async def test_langfuse_groups_requests_by_agent_slug_and_context_id(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", content="same context")
        headers = {
            "X-Orchestra-Agent-Slug": "orchestra",
            "X-Orchestra-Context-Id": "ctx-001",
        }
        payload = {
            "instructions": "You are a helper.",
            "input_items": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
            "tools": None,
        }
        await self._request("POST", "/v1/responses", payload, headers=headers)
        await self._request("POST", "/v1/responses", payload, headers=headers)
        self.assertEqual(len(self.telemetry.requests), 2)
        self.assertEqual(self.telemetry.requests[0]["group_key"], "orchestra:ctx-001")
        self.assertEqual(self.telemetry.requests[1]["group_key"], "orchestra:ctx-001")
        self.assertEqual(self.telemetry.requests[0]["metadata"]["request_kind"], "responses")
        self.assertEqual(
            self.telemetry.requests[0]["success"]["metadata"]["selected_transport"], "codex"
        )

    async def test_langfuse_rotates_group_after_context_change(self) -> None:
        self.upstream.set_codex_behavior("acct-primary", content="context reply")
        payload = {
            "instructions": "You are a helper.",
            "input_items": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
            "tools": None,
        }
        await self._request(
            "POST",
            "/v1/responses",
            payload,
            headers={"X-Orchestra-Agent-Slug": "orchestra", "X-Orchestra-Context-Id": "ctx-001"},
        )
        await self._request(
            "POST",
            "/v1/responses",
            payload,
            headers={"X-Orchestra-Agent-Slug": "orchestra", "X-Orchestra-Context-Id": "ctx-002"},
        )
        self.assertEqual(len(self.telemetry.requests), 2)
        self.assertNotEqual(
            self.telemetry.requests[0]["group_key"], self.telemetry.requests[1]["group_key"]
        )

    async def test_langfuse_records_fallback_attempt(self) -> None:
        self.upstream.set_codex_behavior(
            "acct-primary", status=503, error="temporarily unavailable"
        )
        self.upstream.set_codex_behavior(
            "acct-secondary", status=503, error="temporarily unavailable"
        )
        self.upstream.set_fallback_behavior(content="fallback reply")
        await self._request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={
                "X-Orchestra-Agent-Slug": "orchestra",
                "X-Orchestra-Context-Id": "ctx-fallback",
            },
        )
        latest = self.telemetry.requests[-1]
        self.assertEqual(latest["group_key"], "orchestra:ctx-fallback")
        self.assertEqual(len(latest["generations"]), 3)
        self.assertEqual(latest["generations"][-1]["name"], "llm_proxy.fallback_attempt")
        self.assertEqual(latest["success"]["metadata"]["selected_transport"], "fallback")
