def main() -> None:
    """Run the template agent-mux backend with shared bootstrap logic."""

    from core.orchestra_agents.agent_mux_runtime.bootstrap import run_backend
    from core.orchestra_agents.templates.agent_mux.agent_runtime.backend import (
        AgentMuxBackend,
    )

    run_backend(
        backend_factory=AgentMuxBackend,
        working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
        agent_slug_fallback="__AGENT_SLUG__",
        backend_type_fallback="__BACKEND_TYPE__",
    )


if __name__ == "__main__":
    main()
