"""Thin MCP server: single send_telegram_message tool via HTTP proxy."""

from __future__ import annotations

import logging
from typing import Any

from telegram_mcp.config import TelegramMCPConfig, load_config
from telegram_mcp.mcp.payloads import tools_result
from telegram_mcp.mcp.protocol import mcp_content
from telegram_mcp.mcp.send import safe_handle_send
from telegram_mcp.telegram_client import TelegramHTTPClient

logger = logging.getLogger(__name__)


class TelegramMCPServer:
    """MCP server: dispatches JSON-RPC requests to the send tool."""

    def __init__(self, *, config: TelegramMCPConfig | None = None) -> None:
        self.config = config or load_config()
        self.client = TelegramHTTPClient(self.config.telegram_events_url)
        self._client_started = False

    async def close(self) -> None:
        """Shut down the HTTP client."""
        await self.client.close()
        self._client_started = False

    async def ensure_client_started(self) -> None:
        """Start the HTTP client if not already started."""
        if self._client_started:
            return
        await self.client.start()
        self._client_started = True

    async def handle_tools_call(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """SGR in-process tool call interface."""
        if name != "send_telegram_message":
            return mcp_content({"ok": False, "error": f"Unknown tool: {name}"})
        return await safe_handle_send(self, arguments)


def telegram_tool_definitions() -> list[dict[str, object]]:
    """Return tool definitions for SGR manifest schema_fn."""
    result = tools_result()
    return list(result["tools"])
