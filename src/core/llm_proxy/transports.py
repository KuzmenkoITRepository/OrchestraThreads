from __future__ import annotations

import importlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from core.llm_proxy import codex_oauth
from core.llm_proxy._accounts_core import upsert_codex_profile
from core.llm_proxy.protocol import (
    CodexModelResponse,
    CodexUpstreamError,
    ToolCallItem,
)

_GPT5_PREFIX = "gpt-5"


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def looks_like_minimax_model(model: str | None) -> bool:
    normalized = str(model or "").strip().lower()
    return (
        normalized.startswith("minimax")
        or normalized.startswith("codex-minimax")
        or "minimax" in normalized
    )


def _resolve_chat_completions_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        raise RuntimeError("Fallback base URL is not configured")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _parse_openai_compat_error(status_code: int, raw: str) -> str:
    try:
        payload = json.loads(raw)
    except Exception:
        return raw or f"HTTP {status_code}"
    if not isinstance(payload, dict):
        return raw or f"HTTP {status_code}"
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return raw or f"HTTP {status_code}"


class OpenAICompatibleTransport:
    @dataclass(frozen=True)
    class Config:
        base_url: str | None
        api_key: str | None
        model: str | None
        request_timeout_seconds: int
        request_retry_attempts: int = 3
        request_retry_backoff_seconds: float = 1.0

    def __init__(
        self,
        *,
        config: Config | None = None,
        **kwargs: Any,
    ) -> None:
        effective_config = config or self.Config(**kwargs)
        self.base_url = (effective_config.base_url or "").strip()
        self.api_key = (effective_config.api_key or "").strip()
        self.model = (effective_config.model or "").strip()
        self.request_timeout_seconds = effective_config.request_timeout_seconds
        self.request_retry_attempts = max(1, int(effective_config.request_retry_attempts))
        self.request_retry_backoff_seconds = max(
            0, float(effective_config.request_retry_backoff_seconds)
        )

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def supports(self, *, model_override: str | None = None) -> bool:
        return bool(self.base_url and ((model_override or "").strip() or self.model))

    def complete_chat(
        self, payload: dict[str, Any], *, model_override: str | None = None
    ) -> dict[str, Any]:
        request_config = self._build_request_config(payload=payload, model_override=model_override)
        response = self._post_with_retries(request_config=request_config)
        if response is None:
            raise RuntimeError("OpenAI-compatible fallback request did not produce a response")
        if response.status_code >= 400:
            raise RuntimeError(_parse_openai_compat_error(response.status_code, response.text))
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Fallback returned a non-object JSON payload")
        return payload

    def _build_request_config(
        self,
        *,
        payload: dict[str, Any],
        model_override: str | None,
    ) -> dict[str, Any]:
        effective_model = str(model_override or payload.get("model") or self.model).strip()
        if not self.base_url or not effective_model:
            raise RuntimeError("OpenAI-compatible fallback is not configured")
        request_payload = dict(payload)
        request_payload["stream"] = False
        request_payload["model"] = effective_model
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return {
            "url": _resolve_chat_completions_url(self.base_url),
            "headers": headers,
            "payload": request_payload,
        }

    def _post_with_retries(self, *, request_config: dict[str, Any]) -> requests.Response | None:
        response: requests.Response | None = None
        for attempt in range(1, self.request_retry_attempts + 1):
            response = self._try_post(request_config=request_config, attempt=attempt)
            if response is None:
                continue
            if response.status_code < 500 or attempt >= self.request_retry_attempts:
                break
            time.sleep(self.request_retry_backoff_seconds * attempt)
        return response

    def _try_post(
        self,
        *,
        request_config: dict[str, Any],
        attempt: int,
    ) -> requests.Response | None:
        try:
            with _session() as session:
                return session.post(
                    request_config["url"],
                    headers=request_config["headers"],
                    json=request_config["payload"],
                    timeout=(10, self.request_timeout_seconds),
                )
        except requests.RequestException as exc:
            if attempt >= self.request_retry_attempts:
                raise RuntimeError(
                    f"OpenAI-compatible fallback request failed after {attempt} attempts: {exc}"
                ) from exc
            time.sleep(self.request_retry_backoff_seconds * attempt)
            return None


class CodexDirectTransport:
    @dataclass(frozen=True)
    class Config:
        model: str
        base_url: str
        auth_profiles_path: Path
        request_timeout_seconds: int
        text_verbosity: str
        reasoning_effort: str | None
        reasoning_summary: str
        temperature: float | None

    def __init__(
        self,
        *,
        config: Config | None = None,
        **kwargs: Any,
    ) -> None:
        effective_config = config or self.Config(**kwargs)
        self.model = effective_config.model
        self.base_url = effective_config.base_url
        self.auth_profiles_path = effective_config.auth_profiles_path
        self.request_timeout_seconds = effective_config.request_timeout_seconds
        self.text_verbosity = effective_config.text_verbosity
        self._reasoning_effort = effective_config.reasoning_effort
        self._reasoning_summary = effective_config.reasoning_summary
        self.temperature = effective_config.temperature
        self._creds_lock = threading.Lock()

    def complete(self, **kwargs: Any) -> CodexModelResponse:
        request = dict(kwargs)
        context = self._build_completion_context(
            request=request,
        )
        state = self._perform_completion_request(
            context=context,
            cancel_event=request.get("cancel_event"),
            profile_id=str(request.get("profile_id") or ""),
        )
        response_items = state["response_items"]
        stop_reason = state["stop_reason"]
        if any(isinstance(item, ToolCallItem) for item in response_items) and stop_reason == "stop":
            stop_reason = "tool_use"
        return CodexModelResponse(
            items=response_items,
            stop_reason=stop_reason,
            usage=state["usage"],
            model=str(context["body"]["model"]),
        )

    def _build_completion_context(
        self,
        *,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        profile_id = str(request.get("profile_id") or "")
        creds = self._ensure_credentials(profile_id)
        body = self._build_request_body(
            request=request,
        )
        return {
            "url": codex_oauth.resolve_codex_url(self.base_url),
            "headers": codex_oauth.build_headers(
                creds["access"],
                str(creds["accountId"]),
                request.get("session_id"),
            ),
            "body": body,
        }

    def _build_request_body(
        self,
        *,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.get("model") or self.model,
            "store": False,
            "stream": True,
            "instructions": request.get("instructions") or "You are a helpful assistant.",
            "input": request.get("input_items") or [],
            "text": {"verbosity": request.get("text_verbosity") or self.text_verbosity},
            "include": ["reasoning.encrypted_content"],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        if request.get("session_id"):
            body["prompt_cache_key"] = request["session_id"]
        if request.get("tools"):
            body["tools"] = request["tools"]
        effective_temperature = (
            self.temperature if request.get("temperature") is None else request.get("temperature")
        )
        model_name = str(body["model"]).strip().lower()
        supports_temperature = not model_name.startswith(_GPT5_PREFIX)
        if effective_temperature is not None and supports_temperature:
            body["temperature"] = effective_temperature
        effective_effort = (
            self._reasoning_effort
            if request.get("reasoning_effort") is None
            else request.get("reasoning_effort")
        )
        if effective_effort:
            body["reasoning"] = {
                "effort": codex_oauth.clamp_reasoning_effort(body["model"], effective_effort),
                "summary": request.get("reasoning_summary") or self._reasoning_summary,
            }
        return body

    def _perform_completion_request(
        self,
        *,
        context: dict[str, Any],
        cancel_event: threading.Event | None,
        profile_id: str,
    ) -> dict[str, Any]:
        state: dict[str, Any] = {
            "response_items": [],
            "current_text": None,
            "current_tool": None,
            "usage": None,
            "stop_reason": "stop",
        }
        try:
            with (
                _session() as session,
                session.post(
                    context["url"],
                    headers=context["headers"],
                    json=context["body"],
                    stream=True,
                    timeout=(10, self.request_timeout_seconds),
                ) as response,
            ):
                self._raise_for_error_response(response=response, profile_id=profile_id)
                stream_module = importlib.import_module("core.llm_proxy.transports_stream")
                state = stream_module.consume_codex_stream(
                    response=response,
                    profile_id=profile_id,
                    cancel_event=cancel_event,
                )
        except requests.RequestException as exc:
            raise CodexUpstreamError(
                f"Codex request failed: {exc}",
                profile_id=profile_id,
                retriable=True,
                account_unavailable=True,
            ) from exc
        return state

    def _raise_for_error_response(
        self,
        *,
        response: requests.Response,
        profile_id: str,
    ) -> None:
        if response.status_code < 400:
            return
        message = codex_oauth.parse_error_payload(response.status_code, response.text)
        raise CodexUpstreamError(
            message,
            profile_id=profile_id,
            status_code=response.status_code,
            retriable=(
                response.status_code >= 500
                or response.status_code == 429
                or codex_oauth.is_retryable_codex_error_message(message)
            ),
            account_unavailable=(
                response.status_code in {401, 403, 429}
                or codex_oauth.is_account_unavailable_message(message)
            ),
        )

    def _ensure_credentials(self, profile_id: str) -> dict[str, Any]:
        with self._creds_lock:
            _, creds, _ = codex_oauth.pick_openclaw_profile(self.auth_profiles_path, profile_id)
            fresh, refreshed = codex_oauth.ensure_fresh_credentials(creds)
            if refreshed:
                upsert_codex_profile(self.auth_profiles_path, profile_id, fresh, promote=False)
            return dict(fresh)
