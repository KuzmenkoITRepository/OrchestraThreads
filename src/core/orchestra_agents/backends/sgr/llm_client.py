from __future__ import annotations

from typing import Any

import aiohttp

from core.orchestra_agents.backends.agent_mux.normalization import sanitize_reply_text
from core.orchestra_agents.backends.sgr import llm_response as _response
from core.orchestra_agents.backends.sgr import llm_transport as _transport
from core.orchestra_agents.backends.sgr import model_routing as _model_routing

_OMNIROUTE_TRACE_AGENT_HEADER = "X-OmniRoute-Trace-Agent"
_OMNIROUTE_TRACE_CONTEXT_HEADER = "X-OmniRoute-Trace-Context"


class SGRLLMClient:
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
        session = await self._ensure_session()
        request_payload = dict(payload)
        if _model_routing.requires_streaming_chat(_payload_model(request_payload)):
            request_payload["stream"] = True
        async with session.post(
            _transport.chat_completions_url(self._route_policy),
            json=request_payload,
            headers=_transport.build_headers(
                agent_slug=self._agent_slug,
                payload=request_payload,
                trace_agent_header=_OMNIROUTE_TRACE_AGENT_HEADER,
                trace_context_header=_OMNIROUTE_TRACE_CONTEXT_HEADER,
            ),
        ) as response:
            if response.status >= 400:
                raw = await response.text()
                raise RuntimeError(f"omniroute chat request failed: HTTP {response.status}: {raw}")
            if request_payload.get("stream"):
                return _response.stream_payload(await _read_stream_lines(response))
            raw = await response.text()
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


async def _read_stream_lines(response: aiohttp.ClientResponse) -> list[str]:
    lines: list[str] = []
    while True:
        line = await _decoded_stream_line(response)
        if line is None:
            break
        if _append_and_should_stop(lines, line):
            break
    return lines


def _payload_model(payload: dict[str, Any]) -> str | None:
    raw_model = payload.get("model")
    if raw_model is None:
        return None
    text = str(raw_model).strip()
    return text or None


async def _decoded_stream_line(response: aiohttp.ClientResponse) -> str | None:
    raw_line = await response.content.readline()
    if not raw_line:
        return None
    return raw_line.decode("utf-8", errors="replace").rstrip("\r\n")


def _is_stream_done(line: str) -> bool:
    return line.startswith("data:") and line[5:].strip() == "[DONE]"


def _append_and_should_stop(lines: list[str], line: str) -> bool:
    if not line:
        return False
    lines.append(line)
    return _is_stream_done(line)
