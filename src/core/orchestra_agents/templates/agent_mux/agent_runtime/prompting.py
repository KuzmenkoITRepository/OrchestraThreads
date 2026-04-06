"""Backward-compatible re-export from shared agent_mux_runtime."""

from core.orchestra_agents.agent_mux_runtime.prompt_builder import (  # noqa: F401, WPS412
    build_compact_wakeup_block as build_compact_wakeup_block,
)
from core.orchestra_agents.agent_mux_runtime.prompt_builder import (
    build_context_memory_block as build_context_memory_block,
)
