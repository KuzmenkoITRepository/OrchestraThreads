"""LLM proxy HTTP client for the SGR Minimax agent."""

from __future__ import annotations

import json
from typing import Any

import aiohttp
from core.llm_proxy.client_config import (
    LLM_PROXY_TRACE_AGENT_HEADER,
    LLM_PROXY_TRACE_CONTEXT_HEADER,
    build_llm_proxy_openai_base_url,
    resolve_llm_proxy_api_key,
)
from core.llm_proxy.protocol import (
    openai_chat_payload_to_codex_response,
    tool_calls_to_openai,
)
from core.orchestra_agents.agent_mux_runtime import sanitize_reply_text


def _chat_completions_url(route_policy: str) -> str:
    base = build_llm_proxy_openai_base_url(route_policy).rstrip("/")
    return f"{base}/chat/completions"


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
        response = openai_chat_payload_to_codex_response(payload)
        self.last_model = response.model or default_model
        text = sanitize_reply_text(response.text)
        msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        tool_calls = tool_calls_to_openai(response.tool_calls)
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg, text, tool_calls or []

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout_val = max(1.0, float(self._timeout_seconds or 120))
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_val))
        return self._session

    def _build_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            LLM_PROXY_TRACE_AGENT_HEADER: self._agent_slug,
            LLM_PROXY_TRACE_CONTEXT_HEADER: str(payload.get("thread_id") or self._agent_slug),
        }
        api_key = resolve_llm_proxy_api_key()
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
