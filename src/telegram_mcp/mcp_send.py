"""Send-tool handler for Telegram MCP server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram_mcp.mcp_payloads import ensure_text, normalize_optional_str
from telegram_mcp.mcp_protocol import JsonDict, mcp_content

if TYPE_CHECKING:
    from telegram_mcp.mcp_server import TelegramMCPServer

logger = logging.getLogger(__name__)


async def handle_send(
    server: TelegramMCPServer,
    arguments: JsonDict,
) -> JsonDict:
    """Handle send_telegram_message tool call."""
    message = ensure_text(arguments.get("message"), field_name="message")
    recipient = normalize_optional_str(arguments.get("recipient"))
    chat_id = server.config.resolve_chat_id(recipient)
    await server.ensure_client_started()
    send_result = await server.client.send_message(chat_id, message)
    alias = recipient or server.config.defaults.default_recipient
    if not send_result.get("ok"):
        return _failure_result(send_result, chat_id=chat_id, alias=alias)
    return _success_result(send_result, chat_id=chat_id, alias=alias)


def _failure_result(
    send_result: JsonDict,
    *,
    chat_id: int,
    alias: str,
) -> JsonDict:
    return mcp_content(
        {
            "ok": False,
            "error": str(send_result.get("error") or "Telegram send failed"),
            "chat_id": chat_id,
            "recipient": alias,
        }
    )


def _success_result(
    send_result: JsonDict,
    *,
    chat_id: int,
    alias: str,
) -> JsonDict:
    return mcp_content(
        {
            "ok": True,
            "message_id": int(send_result.get("message_id") or 0),
            "chat_id": chat_id,
            "recipient": alias,
        }
    )


async def safe_handle_send(
    server: TelegramMCPServer,
    arguments: JsonDict,
) -> JsonDict:
    """Run handle_send, wrapping any error as MCP content."""
    try:
        return await handle_send(server, arguments)
    except Exception as exc:
        logger.error("send_telegram_message error: %s", exc, exc_info=True)
        return mcp_content({"ok": False, "error": str(exc)})
