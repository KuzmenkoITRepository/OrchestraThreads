"""Stable facade for agent_mux dispatch helpers."""

from __future__ import annotations

from core.orchestra_agents.backends.agent_mux.dispatch.engine import (
    AgentMuxDispatchSpec as AgentMuxDispatchSpec,
)
from core.orchestra_agents.backends.agent_mux.dispatch.engine import (
    _nonempty_lines as _nonempty_lines,
)
from core.orchestra_agents.backends.agent_mux.dispatch.engine import (
    _parse_json_object as _parse_json_object,
)
from core.orchestra_agents.backends.agent_mux.dispatch.engine import (
    build_agent_mux_command as build_agent_mux_command,
)
from core.orchestra_agents.backends.agent_mux.dispatch.engine import (
    parse_agent_mux_result as parse_agent_mux_result,
)
