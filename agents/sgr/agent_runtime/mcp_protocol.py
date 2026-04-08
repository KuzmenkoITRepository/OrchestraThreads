"""MCP server protocol for tool execution injection."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MCPServerProtocol(Protocol):
    """Protocol for MCP servers that handle tool calls."""

    async def handle_tools_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call and return the result."""
        ...

    async def close(self) -> None:
        """Shut down the MCP server."""
        ...
