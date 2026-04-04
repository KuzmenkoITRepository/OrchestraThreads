from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from .accounts import upsert_codex_profile
from .codex_oauth import (
    build_headers,
    clamp_reasoning_effort,
    ensure_fresh_credentials,
    parse_error_payload,
    pick_openclaw_profile,
    resolve_codex_url,
)
from .protocol import (
    AssistantTextItem,
    CodexModelResponse,
    CodexUpstreamError,
    ToolCallItem,
)


def codex_supports_temperature(model: str) -> bool:
    normalized = (model or "").strip().lower()
    if not normalized:
        return True
    return not normalized.startswith("gpt-5")


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


def resolve_chat_completions_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        raise RuntimeError("Fallback base URL is not configured")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def parse_openai_compat_error(status_code: int, raw: str) -> str:
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


def _message_has_any(message: str, *markers: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in markers)


def is_account_unavailable_message(message: str) -> bool:
    return _message_has_any(
        message,
        "usage limit",
        "rate limit",
        "usage_limit_reached",
        "usage_not_included",
        "rate_limit_exceeded",
        "unauthorized",
        "forbidden",
        "expired",
        "missing access token",
        "missing refresh token",
        "profile ",
        "not found in",
        "temporarily unavailable",
    )


def is_retryable_codex_error_message(message: str) -> bool:
    return is_account_unavailable_message(message) or _message_has_any(
        message,
        "timed out",
        "request failed",
        "connection reset",
        "connection aborted",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "internal server error",
        "codex response failed",
        "request cancelled",
    )


class OpenAICompatibleTransport:
    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        model: str | None,
        request_timeout_seconds: int,
        request_retry_attempts: int = 3,
        request_retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = (base_url or "").strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.request_timeout_seconds = request_timeout_seconds
        self.request_retry_attempts = max(1, int(request_retry_attempts))
        self.request_retry_backoff_seconds = max(0.0, float(request_retry_backoff_seconds))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def supports(self, *, model_override: str | None = None) -> bool:
        return bool(self.base_url and ((model_override or "").strip() or self.model))

    def complete_chat(
        self, payload: dict[str, Any], *, model_override: str | None = None
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
        url = resolve_chat_completions_url(self.base_url)
        response: requests.Response | None = None
        for attempt in range(1, self.request_retry_attempts + 1):
            try:
                with _session() as session:
                    response = session.post(
                        url,
                        headers=headers,
                        json=request_payload,
                        timeout=(10, self.request_timeout_seconds),
                    )
            except requests.RequestException as exc:
                if attempt >= self.request_retry_attempts:
                    raise RuntimeError(
                        f"OpenAI-compatible fallback request failed after {attempt} attempts: {exc}"
                    ) from exc
                time.sleep(self.request_retry_backoff_seconds * attempt)
                continue
            if response.status_code < 500 or attempt >= self.request_retry_attempts:
                break
            time.sleep(self.request_retry_backoff_seconds * attempt)
        if response is None:
            raise RuntimeError("OpenAI-compatible fallback request did not produce a response")
        if response.status_code >= 400:
            raise RuntimeError(parse_openai_compat_error(response.status_code, response.text))
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Fallback returned a non-object JSON payload")
        return payload


class CodexDirectTransport:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        auth_profiles_path: Path,
        request_timeout_seconds: int,
        text_verbosity: str,
        reasoning_effort: str | None,
        reasoning_summary: str,
        temperature: float | None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.auth_profiles_path = auth_profiles_path
        self.request_timeout_seconds = request_timeout_seconds
        self.text_verbosity = text_verbosity
        self.reasoning_effort = reasoning_effort
        self.reasoning_summary = reasoning_summary
        self.temperature = temperature
        self._creds_lock = threading.Lock()

    def _ensure_credentials(self, profile_id: str) -> dict[str, Any]:
        with self._creds_lock:
            _, creds, _ = pick_openclaw_profile(self.auth_profiles_path, profile_id)
            fresh, refreshed = ensure_fresh_credentials(creds)
            if refreshed:
                upsert_codex_profile(self.auth_profiles_path, profile_id, fresh, promote=False)
            return dict(fresh)

    def complete(
        self,
        *,
        profile_id: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        session_id: str | None,
        cancel_event: threading.Event | None,
        model: str | None = None,
        text_verbosity: str | None = None,
        reasoning_effort: str | None = None,
        reasoning_summary: str | None = None,
        temperature: float | None = None,
    ) -> CodexModelResponse:
        creds = self._ensure_credentials(profile_id)
        url = resolve_codex_url(self.base_url)
        headers = build_headers(creds["access"], str(creds["accountId"]), session_id)
        body: dict[str, Any] = {
            "model": model or self.model,
            "store": False,
            "stream": True,
            "instructions": instructions or "You are a helpful assistant.",
            "input": input_items,
            "text": {"verbosity": text_verbosity or self.text_verbosity},
            "include": ["reasoning.encrypted_content"],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        if session_id:
            body["prompt_cache_key"] = session_id
        if tools:
            body["tools"] = tools
        effective_temperature = self.temperature if temperature is None else temperature
        if effective_temperature is not None and codex_supports_temperature(str(body["model"])):
            body["temperature"] = effective_temperature
        effective_effort = (
            reasoning_effort if reasoning_effort is not None else self.reasoning_effort
        )
        if effective_effort:
            body["reasoning"] = {
                "effort": clamp_reasoning_effort(body["model"], effective_effort),
                "summary": reasoning_summary or self.reasoning_summary,
            }
        response_items: list[Any] = []
        current_text: AssistantTextItem | None = None
        current_tool: ToolCallItem | None = None
        usage: dict[str, Any] | None = None
        stop_reason = "stop"
        try:
            with (
                _session() as session,
                session.post(
                    url,
                    headers=headers,
                    json=body,
                    stream=True,
                    timeout=(10, self.request_timeout_seconds),
                ) as response,
            ):
                if response.status_code >= 400:
                    message = parse_error_payload(response.status_code, response.text)
                    raise CodexUpstreamError(
                        message,
                        profile_id=profile_id,
                        status_code=response.status_code,
                        retriable=(
                            response.status_code >= 500
                            or response.status_code == 429
                            or is_retryable_codex_error_message(message)
                        ),
                        account_unavailable=(
                            response.status_code in {401, 403, 429}
                            or is_account_unavailable_message(message)
                        ),
                    )
                for raw_line in response.iter_lines(decode_unicode=True):
                    if isinstance(raw_line, bytes):
                        raw_line = raw_line.decode("utf-8", "replace")
                    if cancel_event is not None and cancel_event.is_set():
                        response.close()
                        raise CodexUpstreamError(
                            "Codex request cancelled",
                            profile_id=profile_id,
                            retriable=True,
                        )
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    payload = raw_line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or "")
                    if event_type == "error":
                        message = str(event.get("message") or event.get("code") or event)
                        raise CodexUpstreamError(
                            f"Codex error: {message}",
                            profile_id=profile_id,
                            retriable=is_retryable_codex_error_message(message),
                            account_unavailable=is_account_unavailable_message(message),
                        )
                    if event_type == "response.failed":
                        error_payload = event.get("response", {}).get("error", {})
                        if isinstance(error_payload, dict) and error_payload.get("message"):
                            message = str(error_payload["message"])
                            raise CodexUpstreamError(
                                message,
                                profile_id=profile_id,
                                retriable=is_retryable_codex_error_message(message),
                                account_unavailable=is_account_unavailable_message(message),
                            )
                        raise CodexUpstreamError(
                            "Codex response failed",
                            profile_id=profile_id,
                            retriable=True,
                        )
                    if event_type == "response.output_item.added":
                        item = event.get("item", {})
                        if not isinstance(item, dict):
                            continue
                        item_type = str(item.get("type") or "")
                        if item_type == "message":
                            current_text = AssistantTextItem(
                                item_id=str(item.get("id") or f"msg_{uuid.uuid4().hex[:8]}")
                            )
                            response_items.append(current_text)
                            current_tool = None
                        elif item_type == "function_call":
                            current_tool = ToolCallItem(
                                call_id=str(item.get("call_id") or f"call_{uuid.uuid4().hex[:8]}"),
                                item_id=str(item.get("id") or f"fc_{uuid.uuid4().hex[:8]}"),
                                name=str(item.get("name") or ""),
                                arguments_json=str(item.get("arguments") or "{}"),
                            )
                            response_items.append(current_tool)
                            current_text = None
                        continue
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str) and current_text is not None:
                            current_text.text += delta
                        continue
                    if event_type == "response.function_call_arguments.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str) and current_tool is not None:
                            current_tool.arguments_json += delta
                            try:
                                current_tool.arguments = json.loads(current_tool.arguments_json)
                            except Exception:
                                pass
                        continue
                    if event_type == "response.function_call_arguments.done":
                        if current_tool is not None:
                            arguments = event.get("arguments")
                            if isinstance(arguments, str) and arguments.strip():
                                current_tool.arguments_json = arguments
                                try:
                                    current_tool.arguments = json.loads(arguments)
                                except Exception:
                                    current_tool.arguments = {}
                        continue
                    if event_type == "response.output_item.done":
                        item = event.get("item", {})
                        if not isinstance(item, dict):
                            continue
                        item_type = str(item.get("type") or "")
                        if item_type == "message" and current_text is not None:
                            content_parts = item.get("content")
                            if isinstance(content_parts, list):
                                parts: list[str] = []
                                for part in content_parts:
                                    if not isinstance(part, dict):
                                        continue
                                    if part.get("type") == "output_text" and isinstance(
                                        part.get("text"), str
                                    ):
                                        parts.append(part["text"])
                                    elif part.get("type") == "refusal" and isinstance(
                                        part.get("refusal"), str
                                    ):
                                        parts.append(part["refusal"])
                                if parts:
                                    current_text.text = "".join(parts).strip()
                            current_text = None
                        elif item_type == "function_call" and current_tool is not None:
                            arguments = item.get("arguments")
                            if isinstance(arguments, str) and arguments.strip():
                                current_tool.arguments_json = arguments
                                try:
                                    current_tool.arguments = json.loads(arguments)
                                except Exception:
                                    current_tool.arguments = {}
                            current_tool = None
                        continue
                    if event_type in {"response.completed", "response.done"}:
                        response_payload = event.get("response", {})
                        if isinstance(response_payload, dict):
                            usage = response_payload.get("usage")
                            status = (
                                str(response_payload.get("status") or "completed").strip().lower()
                            )
                            if status in {"failed", "cancelled"}:
                                stop_reason = "error"
                            elif status == "incomplete":
                                stop_reason = "length"
                            else:
                                stop_reason = "stop"
                        break
        except requests.RequestException as exc:
            raise CodexUpstreamError(
                f"Codex request failed: {exc}",
                profile_id=profile_id,
                retriable=True,
                account_unavailable=True,
            ) from exc
        if any(isinstance(item, ToolCallItem) for item in response_items) and stop_reason == "stop":
            stop_reason = "tool_use"
        return CodexModelResponse(
            items=response_items,
            stop_reason=stop_reason,
            usage=usage,
            model=str(body["model"]),
        )
