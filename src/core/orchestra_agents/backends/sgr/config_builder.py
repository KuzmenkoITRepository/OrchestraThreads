"""Compatibility facade for SGR runtime configuration construction."""

from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.agent_mux.normalization import (
    normalize_bool as _normalize_bool,
)
from core.orchestra_agents.backends.sgr.config.builder import (
    SGRLLMConfig as SGRLLMConfig,
)
from core.orchestra_agents.backends.sgr.config.builder import (
    _resolved_model as _resolved_model,
)
from core.orchestra_agents.backends.sgr.config.builder import (
    _resolved_route_policy as _resolved_route_policy,
)
from core.orchestra_agents.backends.sgr.config.builder import (
    build_llm_config as _build_llm_config,
)
from core.orchestra_agents.backends.sgr.config.builder import (
    build_settings as _build_settings,
)
from core.orchestra_agents.backends.sgr.support import SGRRuntimeSettings


def build_llm_config(raw: dict[str, Any]) -> SGRLLMConfig:
    """Build LLM config from raw config dict and environment."""
    return _build_llm_config(raw)


def build_settings(raw: dict[str, Any]) -> SGRRuntimeSettings:
    """Build SGRRuntimeSettings from raw config dict and environment."""
    return _build_settings(raw, normalize_bool=_normalize_bool)
