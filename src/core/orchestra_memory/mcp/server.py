from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Protocol

from core.orchestra_memory.client import OrchestraMemoryClient
from core.orchestra_memory.mcp.protocol import handle_tools_call, list_tools, resolve_request
from core.orchestra_thread.mcp.transport import encode_message, read_message

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"


class _MemoryClientProtocol(Protocol):
    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, Any]: ...

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool: ...

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int: ...

    async def close(self) -> None: ...


class OrchestraMemoryMCPServer:
    def __init__(
        self,
        *,
        agent_slug: str | None = None,
        client: _MemoryClientProtocol | None = None,
    ) -> None:
        normalized_agent_slug = str(agent_slug or os.getenv("ORCHESTRA_AGENT_SLUG") or "").strip()
        if not normalized_agent_slug:
            raise RuntimeError("ORCHESTRA_AGENT_SLUG is required")
        self.agent_slug = normalized_agent_slug
        self.client = client or OrchestraMemoryClient()

    def handle_initialize(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {
                "name": "orchestra-memory-mcp",
                "version": "0.1.0",
            },
        }

    def handle_tools_list(self) -> dict[str, Any]:
        return {"tools": list_tools()}

    async def handle_tools_call(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await handle_tools_call(self, name=name, arguments=arguments)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        return await resolve_request(self, request=request, logger=logger)

    async def close(self) -> None:
        await self.client.close()


async def main_async() -> None:
    server = OrchestraMemoryMCPServer()
    framing: str | None = None
    try:
        while True:
            request, framing = await read_message(sys.stdin.buffer, framing_hint=framing)
            if request is None:
                break
            response = await server.handle_request(request)
            if response is not None:
                sys.stdout.buffer.write(encode_message(response, framing=framing or "newline"))
                sys.stdout.buffer.flush()
    except Exception:
        raise
    finally:
        await server.close()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main_async())


def orchestra_memory_tool_definitions() -> list[dict[str, object]]:
    """Return tool definitions for SGR inline MCP loading."""
    return [dict(td) for td in list_tools()]


if __name__ == "__main__":
    main()
