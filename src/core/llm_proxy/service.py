from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiohttp import web

from .client_config import (
    LLM_PROXY_TRACE_AGENT_HEADER,
    LLM_PROXY_TRACE_CONTEXT_HEADER,
    LLM_PROXY_TRACE_SESSION_HEADER,
    LLM_PROXY_TRACE_USER_HEADER,
    ROUTE_POLICY_CODEX_ONLY,
    ROUTE_POLICY_MANAGED_AUTO,
    ROUTE_POLICY_MINIMAX_ONLY,
)
from .protocol import (
    AllCodexAccountsUnavailable,
    codex_response_to_dict,
    codex_response_stream_events,
    completion_stream_chunks,
    normalize_responses_input_items,
)
from .langfuse import LangfuseTelemetry, TelemetrySettings
from .router import UnifiedLLMRouter
from .transports import is_retryable_codex_error_message


DEFAULT_MODEL = "gpt-5.4"
DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
DEFAULT_SYSTEM_INSTRUCTIONS = "You are a helpful assistant."
DEFAULT_ACCOUNT_FAILURE_COOLDOWN_SECONDS = 120
DEFAULT_FALLBACK_TIMEOUT_SECONDS = 120
RATE_LIMIT_MARKERS = (
    "rate limit",
    "usage limit",
    "rate_limit",
    "usage_limit",
)


@dataclass
class ProxyConfig:
    host: str
    port: int
    model: str
    base_url: str
    auth_profiles_path: Path
    profile_id: str | None
    profile_ids: tuple[str, ...]
    default_system_instructions: str
    text_verbosity: str
    reasoning_effort: str | None
    reasoning_summary: str
    temperature: float | None
    request_timeout_seconds: int
    account_failure_cooldown_seconds: int
    rotation_state_path: Path
    fallback_base_url: str | None
    fallback_api_key: str | None
    fallback_model: str | None
    fallback_timeout_seconds: int
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None
    langfuse_environment: str | None = None
    langfuse_release: str | None = None


def classify_proxy_exception_status(exc: Exception) -> int:
    if isinstance(exc, AllCodexAccountsUnavailable):
        return 503
    message = str(exc).strip().lower()
    if any(marker in message for marker in RATE_LIMIT_MARKERS):
        return 429
    if (
        "all codex accounts unavailable" in message
        or "no codex oauth profiles are available" in message
        or "fallback failed" in message
        or "temporarily unavailable" in message
        or is_retryable_codex_error_message(message)
    ):
        return 503
    return 500


def resolve_route_policy(path: str, *, endpoint: str) -> str | None:
    normalized = path.rstrip("/")
    if endpoint == "chat":
        if normalized == "/v1/chat/completions":
            return ROUTE_POLICY_MANAGED_AUTO
        if normalized == "/codex/v1/chat/completions":
            return ROUTE_POLICY_CODEX_ONLY
        if normalized == "/minimax/v1/chat/completions":
            return ROUTE_POLICY_MINIMAX_ONLY
        return None
    if endpoint == "codex":
        if normalized == "/v1/responses":
            return ROUTE_POLICY_MANAGED_AUTO
        if normalized == "/codex/v1/responses":
            return ROUTE_POLICY_CODEX_ONLY
        if normalized == "/minimax/v1/responses":
            return ROUTE_POLICY_MINIMAX_ONLY
        if normalized == "/v1/codex/responses":
            return ROUTE_POLICY_MANAGED_AUTO
        if normalized == "/codex/v1/codex/responses":
            return ROUTE_POLICY_CODEX_ONLY
        if normalized == "/minimax/v1/codex/responses":
            return ROUTE_POLICY_MINIMAX_ONLY
        return None
    if endpoint == "models":
        if normalized in {"/v1/models", "/codex/v1/models", "/minimax/v1/models"}:
            return ROUTE_POLICY_MANAGED_AUTO
    return None


class LLMProxyService:
    def __init__(self, config: ProxyConfig, *, telemetry: LangfuseTelemetry | None = None) -> None:
        self.config = config
        self.telemetry = telemetry or LangfuseTelemetry(
            TelemetrySettings(
                enabled=bool(config.langfuse_enabled),
                public_key=config.langfuse_public_key,
                secret_key=config.langfuse_secret_key,
                base_url=config.langfuse_base_url,
                environment=config.langfuse_environment,
                release=config.langfuse_release,
            )
        )
        self.router = UnifiedLLMRouter(
            model=config.model,
            base_url=config.base_url,
            auth_profiles_path=config.auth_profiles_path,
            profile_id=config.profile_id,
            request_timeout_seconds=config.request_timeout_seconds,
            text_verbosity=config.text_verbosity,
            reasoning_effort=config.reasoning_effort,
            reasoning_summary=config.reasoning_summary,
            temperature=config.temperature,
            profile_ids=config.profile_ids,
            rotation_state_path=config.rotation_state_path,
            account_failure_cooldown_seconds=config.account_failure_cooldown_seconds,
            fallback_base_url=config.fallback_base_url,
            fallback_api_key=config.fallback_api_key,
            fallback_model=config.fallback_model,
            fallback_timeout_seconds=config.fallback_timeout_seconds,
            telemetry=self.telemetry,
        )

    async def health_snapshot(self) -> tuple[dict[str, Any], int]:
        try:
            accounts_payload = await asyncio.to_thread(self.router.describe_accounts)
            accounts_status = 200
        except Exception as exc:
            accounts_payload = {
                "error": {
                    "message": str(exc),
                    "type": exc.__class__.__name__,
                }
            }
            accounts_status = 503
        return (
            {
                "status": "ok" if accounts_status == 200 else "degraded",
                "proxy": "llm_proxy",
                "model": self.config.model,
                "base_url": self.config.base_url,
                "auth_profiles_path": str(self.config.auth_profiles_path),
                "accounts": accounts_payload,
            },
            200,
        )

    async def accounts_snapshot(self) -> tuple[dict[str, Any], int]:
        try:
            return await asyncio.to_thread(self.router.describe_accounts), 200
        except Exception as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": exc.__class__.__name__,
                }
            }, 503

    def models_payload(self) -> dict[str, Any]:
        models = [
            {
                "id": self.config.model,
                "object": "model",
                "owned_by": "llm_proxy",
            }
        ]
        if self.router.fallback_transport.enabled:
            models.append(
                {
                    "id": self.router.fallback_transport.model,
                    "object": "model",
                    "owned_by": "llm_proxy-fallback",
                }
            )
        return {"object": "list", "data": models}

    def trace_metadata_from_request(self, headers: Any, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "agent_slug": (
                str(payload.get("agent_slug") or "").strip()
                or str(headers.get(LLM_PROXY_TRACE_AGENT_HEADER) or "").strip()
                or None
            ),
            "context_id": (
                str(payload.get("context_id") or "").strip()
                or str(headers.get(LLM_PROXY_TRACE_CONTEXT_HEADER) or "").strip()
                or None
            ),
            "langfuse_session_id": (
                str(payload.get("langfuse_session_id") or "").strip()
                or str(headers.get(LLM_PROXY_TRACE_SESSION_HEADER) or "").strip()
                or None
            ),
            "langfuse_user_id": (
                str(payload.get("langfuse_user_id") or "").strip()
                or str(headers.get(LLM_PROXY_TRACE_USER_HEADER) or "").strip()
                or None
            ),
            "thread_id": str(payload.get("thread_id") or "").strip() or None,
            "root_thread_id": str(payload.get("root_thread_id") or "").strip() or None,
            "parent_thread_id": str(payload.get("parent_thread_id") or "").strip() or None,
            "origin_channel": str(payload.get("origin_channel") or "").strip() or None,
            "origin_chat_id": str(payload.get("origin_chat_id") or "").strip() or None,
            "origin_user_id": str(payload.get("origin_user_id") or "").strip() or None,
            "request_scope": str(payload.get("request_scope") or "").strip() or None,
        }
        return {key: value for key, value in metadata.items() if value is not None}

    def shutdown(self) -> None:
        self.telemetry.shutdown()


def build_app(service: LLMProxyService) -> web.Application:
    app = web.Application()

    async def handle_health(_: web.Request) -> web.Response:
        payload, status = await service.health_snapshot()
        return web.json_response(payload, status=status)

    async def handle_accounts(_: web.Request) -> web.Response:
        payload, status = await service.accounts_snapshot()
        return web.json_response(payload, status=status)

    async def handle_models(_: web.Request) -> web.Response:
        return web.json_response(service.models_payload())

    async def handle_post(request: web.Request) -> web.StreamResponse:
        chat_route_policy = resolve_route_policy(request.path, endpoint="chat")
        codex_route_policy = resolve_route_policy(request.path, endpoint="codex")
        if chat_route_policy is None and codex_route_policy is None:
            return web.json_response({"error": {"message": f"Unknown path: {request.path}"}}, status=404)
        try:
            payload = await request.json()
        except Exception as exc:
            return web.json_response(
                {"error": {"message": f"Invalid JSON payload: {exc}"}},
                status=400,
            )
        if not isinstance(payload, dict):
            return web.json_response({"error": {"message": "Expected JSON object"}}, status=400)
        trace_metadata = service.trace_metadata_from_request(request.headers, payload)
        if chat_route_policy is not None:
            trace_metadata.update(
                {
                    "request_kind": "chat_completions",
                    "request_path": request.path,
                    "stream": bool(payload.get("stream", False)),
                }
            )
            try:
                response_payload = await asyncio.to_thread(
                    service.router.complete_openai_chat,
                    payload,
                    service.config.default_system_instructions,
                    route_policy=chat_route_policy,
                    agent_slug=trace_metadata.get("agent_slug"),
                    context_id=trace_metadata.get("context_id"),
                    trace_metadata_overrides=trace_metadata,
                )
            except Exception as exc:
                return web.json_response(
                    {
                        "error": {
                            "message": str(exc),
                            "type": exc.__class__.__name__,
                        }
                    },
                    status=classify_proxy_exception_status(exc),
                )
            if bool(payload.get("stream", False)):
                response = web.StreamResponse(status=200)
                response.headers["Content-Type"] = "text/event-stream; charset=utf-8"
                response.headers["Cache-Control"] = "no-cache"
                response.headers["Connection"] = "keep-alive"
                await response.prepare(request)
                for chunk in completion_stream_chunks(response_payload):
                    event = f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                    await response.write(event)
                await response.write(b"data: [DONE]\n\n")
                await response.write_eof()
                return response
            return web.json_response(response_payload)
        instructions = str(payload.get("instructions") or "").strip()
        input_items = normalize_responses_input_items(payload)
        if input_items is None:
            return web.json_response({"error": {"message": "Expected input or input_items"}}, status=400)
        tools = payload.get("tools")
        if tools is not None and not isinstance(tools, list):
            return web.json_response({"error": {"message": "Expected tools list or null"}}, status=400)
        trace_metadata.update(
            {
                "request_kind": "responses",
                "request_path": request.path,
                "stream": bool(payload.get("stream", False)),
            }
        )
        try:
            response = await asyncio.to_thread(
                service.router.complete,
                instructions=instructions,
                input_items=input_items,
                tools=tools,
                session_id=str(payload.get("session_id") or "").strip() or None,
                cancel_event=None,
                model=str(payload.get("model") or "").strip() or None,
                text_verbosity=str(payload.get("text_verbosity") or "").strip() or None,
                reasoning_effort=str(payload.get("reasoning_effort") or "").strip() or None,
                reasoning_summary=str(payload.get("reasoning_summary") or "").strip() or None,
                temperature=(
                    float(payload.get("temperature"))
                    if payload.get("temperature") is not None
                    else None
                ),
                route_policy=codex_route_policy or ROUTE_POLICY_MANAGED_AUTO,
                agent_slug=trace_metadata.get("agent_slug"),
                context_id=trace_metadata.get("context_id"),
                trace_metadata_overrides=trace_metadata,
            )
        except Exception as exc:
            return web.json_response(
                {
                    "error": {
                        "message": str(exc),
                        "type": exc.__class__.__name__,
                    }
                },
                status=classify_proxy_exception_status(exc),
            )
        if bool(payload.get("stream", False)):
            stream = web.StreamResponse(status=200)
            stream.headers["Content-Type"] = "text/event-stream; charset=utf-8"
            stream.headers["Cache-Control"] = "no-cache"
            stream.headers["Connection"] = "keep-alive"
            await stream.prepare(request)
            for event in codex_response_stream_events(response):
                await stream.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
            await stream.write(b"data: [DONE]\n\n")
            await stream.write_eof()
            return stream
        return web.json_response(codex_response_to_dict(response))

    async def handle_cleanup(_: web.Application) -> None:
        service.shutdown()

    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/accounts/status", handle_accounts)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/codex/v1/models", handle_models)
    app.router.add_get("/minimax/v1/models", handle_models)
    app.router.add_post("/v1/chat/completions", handle_post)
    app.router.add_post("/codex/v1/chat/completions", handle_post)
    app.router.add_post("/minimax/v1/chat/completions", handle_post)
    app.router.add_post("/v1/responses", handle_post)
    app.router.add_post("/codex/v1/responses", handle_post)
    app.router.add_post("/minimax/v1/responses", handle_post)
    app.router.add_post("/v1/codex/responses", handle_post)
    app.router.add_post("/codex/v1/codex/responses", handle_post)
    app.router.add_post("/minimax/v1/codex/responses", handle_post)
    app.on_cleanup.append(handle_cleanup)
    return app
