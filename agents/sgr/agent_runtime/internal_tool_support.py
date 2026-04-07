from __future__ import annotations

from typing import Protocol, cast


class SupportsContextMemory(Protocol):
    def add_entry(
        self,
        *,
        thread_id: str | None,
        entry_type: str,
        text: str,
        metadata_summary: str | None = None,
        event_id: str | None = None,
    ) -> None: ...


class SupportsMCPServer(Protocol):
    async def handle_tools_call(
        self,
        *,
        name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


class SupportsThreadOps(Protocol):
    def ensure_mcp_server(self) -> SupportsMCPServer: ...


class _BackendWithContextMemory(Protocol):
    _context_memory: SupportsContextMemory


class _BackendWithThreadOps(Protocol):
    _thread_ops: SupportsThreadOps


def context_memory(backend: object) -> SupportsContextMemory:
    typed_backend = cast(_BackendWithContextMemory, backend)
    return typed_backend._context_memory


def thread_ops(backend: object) -> SupportsThreadOps:
    typed_backend = cast(_BackendWithThreadOps, backend)
    return typed_backend._thread_ops
