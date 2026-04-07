"""LLM proxy HTTP client for the SGR Minimax agent."""

from __future__ import annotations

from typing import Any

import aiohttp

from agents.sgr.agent_runtime import llm_response as _response
from agents.sgr.agent_runtime import llm_transport as _transport
from core.orchestra_agents.agent_mux_runtime import sanitize_reply_text

_LLM_PROXY_TRACE_AGENT_HEADER = "X-LLM-Proxy-Trace-Agent"
_LLM_PROXY_TRACE_CONTEXT_HEADER = "X-LLM-Proxy-Trace-Context"


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
            _transport.chat_completions_url(self._route_policy),
            json=payload,
            headers=_transport.build_headers(
                agent_slug=self._agent_slug,
                payload=payload,
                trace_agent_header=_LLM_PROXY_TRACE_AGENT_HEADER,
                trace_context_header=_LLM_PROXY_TRACE_CONTEXT_HEADER,
            ),
        ) as response:
            raw = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"llm_proxy chat request failed: HTTP {response.status}: {raw}")
            return _transport.parse_response(raw)

    def extract_completion(
        self,
        payload: dict[str, Any],
        default_model: str,
    ) -> tuple[dict[str, Any], str, list[Any]]:
        """Extract assistant message, text, and tool calls from response."""
        model, text, tool_calls = _response.completion_parts(payload)
        self.last_model = model or default_model
        text = sanitize_reply_text(text)
        msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        openai_tool_calls = list(tool_calls)
        if openai_tool_calls:
            msg["tool_calls"] = openai_tool_calls
        return msg, text, openai_tool_calls or []

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout_val = max(1.0, float(self._timeout_seconds or 120))
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_val))
        return self._session
