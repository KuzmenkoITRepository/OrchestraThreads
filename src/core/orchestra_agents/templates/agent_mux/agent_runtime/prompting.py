"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.agent_mux.internal.context_memory import (
    build_context_memory_block as build_context_memory_block,
)
from core.orchestra_agents.backends.agent_mux.internal.prompt_builder import (
    _base_wakeup_lines as _base_wakeup_lines,
)
from core.orchestra_agents.backends.agent_mux.internal.prompt_builder import (
    _compact_json as _compact_json,
)
from core.orchestra_agents.backends.agent_mux.internal.prompt_builder import (
    _extra_metadata as _extra_metadata,
)
from core.orchestra_agents.backends.agent_mux.internal.prompt_builder import (
    _optional_wakeup_lines as _optional_wakeup_lines,
)
from core.orchestra_agents.backends.agent_mux.internal.prompt_builder import (
    build_compact_wakeup_block as build_compact_wakeup_block,
)
