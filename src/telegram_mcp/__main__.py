"""Main entry point for telegram-mcp MCP server."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from telegram_mcp.mcp.dispatch import dispatch_request
from telegram_mcp.mcp.server import TelegramMCPServer
from telegram_mcp.mcp.transport import encode_message, read_message


async def _run_server() -> None:
    server = TelegramMCPServer()
    framing: str | None = None
    try:  # noqa: WPS501
        while True:
            request, framing = await read_message(
                sys.stdin.buffer,
                framing_hint=framing,
            )
            if request is None:
                break
            response = await dispatch_request(server, request)
            if response is None:
                continue
            encoded = encode_message(response, framing=framing or "newline")
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
    finally:
        await server.close()


def main() -> None:
    """Entry point for the telegram-mcp MCP server."""
    logging.basicConfig(
        level=getattr(
            logging,
            os.getenv("LOG_LEVEL", "INFO").upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run_server())


if __name__ == "__main__":
    main()
