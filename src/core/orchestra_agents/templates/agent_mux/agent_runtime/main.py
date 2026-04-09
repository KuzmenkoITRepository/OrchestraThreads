"""Thin agent-mux template entrypoint using shared runtime bootstrap."""

from __future__ import annotations

from core.orchestra_agents.runtime.bootstrap import run_backend
from core.orchestra_agents.templates.agent_mux.agent_runtime.backend import (
    AgentMuxBackend,
)


def main() -> None:
    run_backend(
        backend_factory=AgentMuxBackend,
        working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
        agent_slug_fallback="__AGENT_SLUG__",
        backend_type_fallback="__BACKEND_TYPE__",
    )


if __name__ == "__main__":
    main()
