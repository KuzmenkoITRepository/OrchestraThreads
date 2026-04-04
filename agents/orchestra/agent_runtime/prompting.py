"""Shared generic agent_mux prompting helpers for the orchestra agent."""

from core.orchestra_agents.templates.agent_mux.agent_runtime.prompting import (
    build_compact_wakeup_block,
    build_context_memory_block,
)

__all__ = ["build_compact_wakeup_block", "build_context_memory_block"]
