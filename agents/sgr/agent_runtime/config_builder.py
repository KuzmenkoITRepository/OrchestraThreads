"""SGR runtime configuration construction."""

from __future__ import annotations

import os
from typing import Any

from core.llm_proxy import client_config as _llm_cfg
from core.orchestra_agents import agent_mux_runtime as _mux_rt

from agents.sgr.agent_runtime import support as _support


def build_llm_raw_config(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "route_policy": raw.get("route_policy") or _llm_cfg.ROUTE_POLICY_MINIMAX_ONLY,
        "model": raw.get("model"),
        "timeout_seconds": raw.get("timeout_seconds"),
        "temperature": raw.get("temperature"),
        "max_tokens": raw.get("max_tokens"),
        "text_verbosity": raw.get("text_verbosity"),
        "reasoning_effort": raw.get("reasoning_effort"),
        "reasoning_summary": raw.get("reasoning_summary"),
    }


def build_settings(raw: dict[str, Any]) -> _support.SGRRuntimeSettings:
    """Build SGRRuntimeSettings from raw config dict and environment."""
    threads_url_raw = raw.get("threads_url")
    if threads_url_raw is None:
        threads_url_raw = os.getenv("ORCHESTRA_THREADS_URL")
    endpoint_raw = raw.get("http_endpoint") or os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or ""
    return _support.SGRRuntimeSettings(
        threads_url=_support.normalize_optional_str(
            threads_url_raw.rstrip("/") if isinstance(threads_url_raw, str) else threads_url_raw
        ),
        http_endpoint=str(endpoint_raw).rstrip("/"),
        heartbeat_interval_seconds=_heartbeat_interval(raw),
        guide_view=_guide_view(raw),
        react_to_inactive=_mux_rt.normalize_bool(raw.get("react_to_inactive"), default=True),
        max_reasoning_steps=_support.normalize_int(
            os.getenv("SGR_MAX_REASONING_STEPS") or raw.get("max_reasoning_steps"),
            default=8,
            minimum=1,
        ),
        max_direct_text_retries=_support.normalize_int(
            os.getenv("SGR_MAX_DIRECT_TEXT_RETRIES") or raw.get("max_direct_text_retries"),
            default=2,
            minimum=0,
        ),
    )


def _heartbeat_interval(raw: dict[str, Any]) -> float:
    return max(
        2.0,
        _mux_rt.normalize_float(
            os.getenv("SGR_HEARTBEAT_INTERVAL_SECONDS") or raw.get("heartbeat_interval_seconds"),
            default=10.0,
        ),
    )


def _guide_view(raw: dict[str, Any]) -> str:
    raw_view = str(raw.get("guide_view") or "compact").strip().lower()
    return raw_view or "compact"
