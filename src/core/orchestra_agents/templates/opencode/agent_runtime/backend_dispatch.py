"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.opencode.backend_dispatch import (
    _LOGGER as _LOGGER,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    _dispatch_once as _dispatch_once,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    _on_dispatch_done as _on_dispatch_done,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    cancel_dispatch as cancel_dispatch,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    classify_events as classify_events,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    dispatch_matches as dispatch_matches,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    fire_dispatch as fire_dispatch,
)
from core.orchestra_agents.backends.opencode.backend_dispatch import (
    run_dispatch as run_dispatch,
)
