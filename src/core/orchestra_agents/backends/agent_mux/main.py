def main() -> None:
    """Run the template agent-mux backend with shared bootstrap logic."""

    from core.orchestra_agents.backends.agent_mux.backend import (
        AgentMuxBackend,
    )
    from core.orchestra_agents.runtime import run_backend

    run_backend(
        backend_factory=AgentMuxBackend,
        working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
        agent_slug_fallback="__AGENT_SLUG__",
        backend_type_fallback="__BACKEND_TYPE__",
    )


if __name__ == "__main__":
    main()
