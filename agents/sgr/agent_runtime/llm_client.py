"""LLM proxy HTTP client for the SGR Minimax agent."""

from __future__ import annotations

import json
import os
from typing import Any

import aiohttp

from core.orchestra_agents.agent_mux_runtime import sanitize_reply_text

_LLM_PROXY_TRACE_AGENT_HEADER = "X-LLM-Proxy-Trace-Agent"
_LLM_PROXY_TRACE_CONTEXT_HEADER = "X-LLM-Proxy-Trace-Context"


def _chat_completions_url(route_policy: str) -> str:
    base = _build_llm_proxy_openai_base_url(route_policy).rstrip("/")
    return f"{base}/chat/completions"


def _build_llm_proxy_openai_base_url(route_policy: str) -> str:
    base_url = os.getenv("LLM_PROXY_URL", "http://orchestra-wet:8100").rstrip("/")
    normalized = str(route_policy or "").strip().lower()
    if normalized == "minimax_only":
        return f"{base_url}/minimax/v1"
    if normalized in {"codex_only", "managed_auto", "fallback", "fallback_only"}:
        return f"{base_url}/v1"
    return f"{base_url}/v1"


def _resolve_llm_proxy_api_key() -> str | None:
    api_key = os.getenv("LLM_PROXY_API_KEY")
    if api_key is None:
        return None
    text = api_key.strip()
    return text or None


def _openai_chat_payload_to_codex_response(  # noqa: WPS210,WPS234
    payload: dict[str, Any],
) -> tuple[str | None, str, list[dict[str, Any]]]:
    model = payload.get("model")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return _optional_str(model), "", []
    choice = choices[0]
    if not isinstance(choice, dict):
        return _optional_str(model), "", []
    message = choice.get("message")
    if not isinstance(message, dict):
        return _optional_str(model), "", []
    text = message.get("content")
    tool_calls = message.get("tool_calls")
    parsed_calls = tool_calls if isinstance(tool_calls, list) else []
    return (
        _optional_str(model),
        _optional_str(text) or "",
        [call for call in parsed_calls if isinstance(call, dict)],
    )


def _tool_calls_to_openai(  # noqa: WPS221
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return list(tool_calls)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class SGRLLMClient:
    """HTTP client for LLM proxy communication."""

    def __init__(
        self,
        agent_slug: str,
        route_policy: str,
        timeout_seconds: float | None,
    ) -> None:
        self._agent_slug = agent_slug
        self._route_policy = route_policy
        self._timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None
        self.last_model: str | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Post a chat completion request to llm_proxy."""
        session = await self._ensure_session()
        async with session.post(
            _chat_completions_url(self._route_policy),
            json=payload,
            headers=self._build_headers(payload),
        ) as response:
            raw = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"llm_proxy chat request failed: HTTP {response.status}: {raw}")
            return self._parse_response(raw)

    def extract_completion(
        self,
        payload: dict[str, Any],
        default_model: str,
    ) -> tuple[dict[str, Any], str, list[Any]]:
        """Extract assistant message, text, and tool calls from response."""
        model, text, tool_calls = _openai_chat_payload_to_codex_response(payload)
        self.last_model = model or default_model
        text = sanitize_reply_text(text)
        msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        openai_tool_calls = _tool_calls_to_openai(tool_calls)
        if openai_tool_calls:
            msg["tool_calls"] = openai_tool_calls
        return msg, text, openai_tool_calls or []

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout_val = max(1.0, float(self._timeout_seconds or 120))
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_val))
        return self._session

    def _build_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            _LLM_PROXY_TRACE_AGENT_HEADER: self._agent_slug,
            _LLM_PROXY_TRACE_CONTEXT_HEADER: str(payload.get("thread_id") or self._agent_slug),
        }
        api_key = _resolve_llm_proxy_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _parse_response(self, raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"llm_proxy returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("llm_proxy returned a non-object payload")
        return parsed
