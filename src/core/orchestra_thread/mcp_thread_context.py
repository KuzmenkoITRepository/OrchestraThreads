from __future__ import annotations

from core.orchestra_thread.mcp_tools_common import JSON_MAP, normalize_optional_str
from core.orchestra_thread.mcp_tools_context import active_context

_CURRENT_THREAD_SENTINELS = frozenset(("current", "active"))


def resolve_thread_id(arguments: JSON_MAP) -> str | None:
    context = active_context()
    requested_thread_id = normalize_optional_str(arguments.get("thread_id"))
    if requested_thread_id in _CURRENT_THREAD_SENTINELS:
        requested_thread_id = None
    return requested_thread_id or normalize_optional_str(context.get("thread_id"))
