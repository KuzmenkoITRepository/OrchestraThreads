from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

from core.orchestra_thread.client import OrchestraThreadsClient
from core.orchestra_thread.mcp_protocol import handle_tools_call, list_tools, resolve_request
from core.orchestra_thread.mcp_transport import encode_message, read_message

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"


class OrchestraThreadsMCPServer:
    def __init__(
        self,
        *,
        agent_slug: str | None = None,
        client: OrchestraThreadsClient | None = None,
    ) -> None:
        normalized_agent_slug = str(
            agent_slug or os.getenv("ORCHESTRA_THREADS_AGENT_SLUG") or os.getenv("AGENT_SLUG") or ""
        ).strip()
        if not normalized_agent_slug:
            raise RuntimeError("ORCHESTRA_THREADS_AGENT_SLUG or AGENT_SLUG is required")
        self.agent_slug = normalized_agent_slug
        self.client = client or OrchestraThreadsClient()

    def handle_initialize(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {
                "name": "orchestra-threads-mcp",
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
    server = OrchestraThreadsMCPServer()
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


def orchestra_threads_tool_definitions() -> list[dict[str, object]]:
    """Return tool definitions for SGR inline MCP loading."""
    return [dict(td) for td in list_tools()]


if __name__ == "__main__":
    main()
