"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.opencode.opencode_client import (
    _REQUEST_TIMEOUT_SECONDS as _REQUEST_TIMEOUT_SECONDS,
)
from core.orchestra_agents.backends.opencode.opencode_client import (
    OpencodeClient as OpencodeClient,
)
from core.orchestra_agents.backends.opencode.opencode_client import (
    close_client as close_client,
)
