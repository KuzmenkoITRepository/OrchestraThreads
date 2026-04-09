from core.orchestra_agents.backends.opencode.backend import OpencodeOmoBackend
from core.orchestra_agents.runtime import run_backend


def main() -> None:
    run_backend(
        backend_factory=OpencodeOmoBackend,
        working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
        agent_slug_fallback="__AGENT_SLUG__",
        backend_type_fallback="__BACKEND_TYPE__",
    )


if __name__ == "__main__":
    main()
