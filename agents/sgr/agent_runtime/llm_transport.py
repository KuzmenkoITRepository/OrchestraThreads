from __future__ import annotations

import json
import os
from typing import Any


def chat_completions_url(route_policy: str) -> str:
    proxy_url = os.getenv("LLM_PROXY_URL", "http://orchestra-wet:8100").rstrip("/")
    if _is_minimax_route(route_policy):
        return f"{proxy_url}/minimax/v1/chat/completions"
    return f"{proxy_url}/v1/chat/completions"


def build_headers(
    *,
    agent_slug: str,
    payload: dict[str, Any],
    trace_agent_header: str,
    trace_context_header: str,
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        trace_agent_header: agent_slug,
        trace_context_header: str(payload.get("thread_id") or agent_slug),
    }
    api_key = _resolve_llm_proxy_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def parse_response(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"llm_proxy returned invalid JSON: {exc}") from exc
    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError("llm_proxy returned a non-object payload")


def _resolve_llm_proxy_api_key() -> str | None:
    api_key = os.getenv("LLM_PROXY_API_KEY")
    if api_key is None:
        return None
    text = api_key.strip()
    return text or None


def _is_minimax_route(route_policy: str) -> bool:
    return str(route_policy or "").strip().lower() == "minimax_only"
