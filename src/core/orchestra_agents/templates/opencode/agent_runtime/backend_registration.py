"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.opencode.backend_registration import (
    _HEARTBEAT_INTERVAL_SECONDS as _HEARTBEAT_INTERVAL_SECONDS,
)
from core.orchestra_agents.backends.opencode.backend_registration import (
    _allowed_peers as _allowed_peers,
)
from core.orchestra_agents.backends.opencode.backend_registration import (
    _heartbeat_loop as _heartbeat_loop,
)
from core.orchestra_agents.backends.opencode.backend_registration import (
    _RegistrationBackend as _RegistrationBackend,
)
from core.orchestra_agents.backends.opencode.backend_registration import (
    register_with_threads as register_with_threads,
)
from core.orchestra_agents.backends.opencode.backend_registration import (
    stop_registration as stop_registration,
)
