from __future__ import annotations

from core.orchestra_thread.mcp_tools_common import JSON_MAP, normalize_optional_str
from core.orchestra_thread.mcp_tools_context import active_context


def resolve_thread_id(arguments: JSON_MAP) -> str | None:
    context = active_context()
    return normalize_optional_str(arguments.get("thread_id")) or normalize_optional_str(
        context.get("thread_id")
    )
