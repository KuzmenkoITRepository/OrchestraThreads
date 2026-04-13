"""Compatibility facade for SGR runtime configuration resolution."""

from __future__ import annotations

from core.orchestra_agents.backends.sgr.config.runtime import (
    RuntimeConfig as RuntimeConfig,
)
from core.orchestra_agents.backends.sgr.config.runtime import _resolve as _resolve
from core.orchestra_agents.backends.sgr.config.runtime import (
    resolve_runtime_config as resolve_runtime_config,
)
