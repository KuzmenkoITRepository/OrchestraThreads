"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.opencode.session_manager import (
    SessionManager as SessionManager,
)
from core.orchestra_agents.backends.opencode.session_manager import (
    _opt_str as _opt_str,
)
from core.orchestra_agents.backends.opencode.session_manager import (
    _persist_mapping as _persist_mapping,
)
from core.orchestra_agents.backends.opencode.session_manager import (
    _read_mapping_file as _read_mapping_file,
)
from core.orchestra_agents.backends.opencode.session_manager import (
    _remove_mapping_file as _remove_mapping_file,
)
from core.orchestra_agents.backends.opencode.session_manager import (
    _require_session_id as _require_session_id,
)
from core.orchestra_agents.backends.opencode.session_manager import (
    _utc_now_iso as _utc_now_iso,
)
