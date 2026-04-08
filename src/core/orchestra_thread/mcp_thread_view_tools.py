from __future__ import annotations

from core.orchestra_thread.mcp_thread_view_current import thread_current as _thread_current_impl
from core.orchestra_thread.mcp_thread_view_expand import thread_expand as _thread_expand_impl
from core.orchestra_thread.mcp_thread_view_guide import thread_guide as _thread_guide_impl
from core.orchestra_thread.mcp_thread_view_peers import thread_peers as _thread_peers_impl


async def thread_current(server: object, arguments: dict[str, object]) -> dict[str, object]:
    return await _thread_current_impl(server, arguments)


async def thread_expand(server: object, arguments: dict[str, object]) -> dict[str, object]:
    return await _thread_expand_impl(server, arguments)


async def thread_guide(server: object, arguments: dict[str, object]) -> dict[str, object]:
    return await _thread_guide_impl(server, arguments)


async def thread_peers(server: object, arguments: dict[str, object]) -> dict[str, object]:
    return await _thread_peers_impl(server, arguments)
