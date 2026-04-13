"""Compatibility facade for the canonical SGR backend entrypoint."""

from __future__ import annotations

from core.orchestra_agents.backends.sgr.runtime.entrypoint import (
    _BackendInit as _BackendInit,
)
from core.orchestra_agents.backends.sgr.runtime.entrypoint import (
    _build_backend_init as _build_backend_init,
)
from core.orchestra_agents.backends.sgr.runtime.entrypoint import (
    _create_backend as _create_backend,
)
from core.orchestra_agents.backends.sgr.runtime.entrypoint import (
    _normalize_config as _normalize_config,
)
from core.orchestra_agents.backends.sgr.runtime.entrypoint import main as main

if __name__ == "__main__":
    main()
