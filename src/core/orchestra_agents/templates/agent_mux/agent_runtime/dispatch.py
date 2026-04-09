"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.agent_mux.codex_config import (
    write_runtime_codex_config as write_runtime_codex_config,
)
from core.orchestra_agents.backends.agent_mux.dispatch_engine import (
    AgentMuxDispatchSpec as AgentMuxDispatchSpec,
)
from core.orchestra_agents.backends.agent_mux.dispatch_engine import (
    _nonempty_lines as _nonempty_lines,
)
from core.orchestra_agents.backends.agent_mux.dispatch_engine import (
    _parse_json_object as _parse_json_object,
)
from core.orchestra_agents.backends.agent_mux.dispatch_engine import (
    build_agent_mux_command as build_agent_mux_command,
)
from core.orchestra_agents.backends.agent_mux.dispatch_engine import (
    parse_agent_mux_result as parse_agent_mux_result,
)
