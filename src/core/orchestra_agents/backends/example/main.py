"""Runtime entrypoint for the canonical example backend."""

from __future__ import annotations

from core.orchestra_agents.backends.example.backend import TemplateBackend
from core.orchestra_agents.runtime import run_backend

_WORKING_DIR_FALLBACK = "/workspace"
_AGENT_SLUG_FALLBACK = "agent"
_BACKEND_TYPE_FALLBACK = "example"


def main() -> None:
    """Run the canonical example backend via the shared bootstrap."""

    run_backend(
        backend_factory=TemplateBackend,
        working_dir_fallback=_WORKING_DIR_FALLBACK,
        agent_slug_fallback=_AGENT_SLUG_FALLBACK,
        backend_type_fallback=_BACKEND_TYPE_FALLBACK,
    )


if __name__ == "__main__":
    main()
