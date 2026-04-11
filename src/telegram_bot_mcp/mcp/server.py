from __future__ import annotations

import asyncio
import logging
import os
import sys

from telegram_bot_mcp.client import TelegramBotListenerClient
from telegram_bot_mcp.config import TelegramBotMCPConfig, load_config
from telegram_bot_mcp.mcp.dispatch import dispatch_request
from telegram_bot_mcp.mcp.protocol import JsonDict
from telegram_bot_mcp.mcp.transport import ProtocolIO

logger = logging.getLogger(__name__)


class TelegramBotMCPServer:  # noqa: WPS214,WPS338 - JSON-RPC server groups transport handlers intentionally.
    def __init__(self, *, config: TelegramBotMCPConfig | None = None) -> None:
        self.config = config or load_config()
        self.client = TelegramBotListenerClient(
            base_url=self.config.listener_url,
            api_token=self.config.listener_api_token,
            timeout_seconds=self.config.timeout_seconds,
        )

    async def close(self) -> None:
        await self.client.close()

    async def handle_request(self, request: JsonDict) -> JsonDict | None:
        return await dispatch_request(self, request)

    async def handle_tools_call(self, name: str, arguments: JsonDict) -> JsonDict:
        from telegram_bot_mcp.mcp.tool_dispatch import handle_tool_call

        return await handle_tool_call(self, name=name, arguments=arguments)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_main_async())


async def _main_async() -> None:
    server = TelegramBotMCPServer()
    framing: str | None = None
    try:  # noqa: WPS501 - runtime must always close the MCP client on exit.
        while True:
            request, framing = await ProtocolIO.read_message(
                sys.stdin.buffer,
                framing_hint=framing,
            )
            if request is None:
                break
            response = await server.handle_request(request)
            if response is None:
                continue
            payload = ProtocolIO.encode_message(response, framing=framing or "newline")
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
    finally:
        await server.close()
