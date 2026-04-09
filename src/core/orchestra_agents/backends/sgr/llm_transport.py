from __future__ import annotations

import json
import os
from typing import Any


def chat_completions_url(route_policy: str) -> str:
    omniroute_url = os.getenv("OMNIROUTE_URL", "http://orchestra-omniroute:20128").rstrip("/")
    return f"{omniroute_url}/v1/chat/completions"


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
        trace_context_header: str(payload.get("agent_slug") or agent_slug),
    }
    api_key = _resolve_omniroute_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def parse_response(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"omniroute returned invalid JSON: {exc}") from exc
    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError("omniroute returned a non-object payload")


def _resolve_omniroute_api_key() -> str | None:
    api_key = os.getenv("OMNIROUTE_API_KEY")
    if api_key is None:
        return None
    text = api_key.strip()
    return text or None
