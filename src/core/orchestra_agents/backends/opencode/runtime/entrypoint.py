from __future__ import annotations

from core.orchestra_agents.backends.opencode.runtime.backend_impl import (
    OpencodeOmoBackend,
)
from core.orchestra_agents.runtime import run_backend


def main() -> None:
    run_backend(
        backend_factory=OpencodeOmoBackend,
        working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
        agent_slug_fallback="__AGENT_SLUG__",
        backend_type_fallback="__BACKEND_TYPE__",
    )
