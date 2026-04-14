from __future__ import annotations

import logging
from typing import Any

from core.telegram_events.listener import telethon
from core.telegram_events.relay_compat_payloads import (
    build_initialize_result,
    build_rpc_error,
    build_send_result,
    build_tools_list_result,
)

logger = logging.getLogger(__name__)

_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32000


def _validate_tool_call(raw_params: Any) -> dict[str, Any]:
    if not isinstance(raw_params, dict):
        msg = "params must be an object"
        raise ValueError(msg)
    tool_name = raw_params.get("name")
    if tool_name != "send_telegram_message":
        msg = f"Unsupported tool: {tool_name}"
        raise ValueError(msg)
    raw_arguments = raw_params.get("arguments")
    if not isinstance(raw_arguments, dict):
        msg = "arguments must be an object"
        raise ValueError(msg)
    return raw_arguments


def _resolve_recipient(arguments: dict[str, Any]) -> str:
    raw_recipient = arguments.get("recipient")
    if not isinstance(raw_recipient, str) or not raw_recipient.strip():
        msg = "chat_id or recipient is required"
        raise ValueError(msg)
    return raw_recipient.strip().lower()


def _resolve_message(arguments: dict[str, Any]) -> str:
    raw_message = arguments.get("message")
    if not isinstance(raw_message, str) or not raw_message.strip():
        msg = "message is required"
        raise ValueError(msg)
    return raw_message


def _resolve_chat_id(arguments: dict[str, Any], recipient_chat_ids: dict[str, str]) -> str:
    raw_chat_id = arguments.get("chat_id")
    if raw_chat_id is not None:
        return str(raw_chat_id)
    recipient = _resolve_recipient(arguments)
    chat_id = recipient_chat_ids.get(recipient)
    if chat_id:
        return chat_id
    msg = f"Unknown recipient: {recipient}"
    raise ValueError(msg)


class RelayCompatRpcHandler:
    def __init__(self, recipient_chat_ids: dict[str, str], listener: Any) -> None:
        self._recipient_chat_ids = recipient_chat_ids
        self._listener = listener

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        if not isinstance(method, str):
            return build_rpc_error(request_id, _INVALID_REQUEST, "method is required")
        if method == "initialize":
            return build_initialize_result(request_id)
        if method == "tools/list":
            return build_tools_list_result(request_id)
        if method != "tools/call":
            return build_rpc_error(request_id, _METHOD_NOT_FOUND, f"Unsupported method: {method}")
        return await self._handle_tools_call(request_id, payload.get("params"))

    async def _handle_tools_call(self, request_id: Any, raw_params: Any) -> dict[str, Any]:
        try:
            message_id = await self._send_from_params(raw_params)
        except ValueError as exc:
            return build_rpc_error(request_id, _INVALID_PARAMS, str(exc))
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc, exc_info=True)
            return build_rpc_error(request_id, _INTERNAL_ERROR, str(exc))
        return build_send_result(request_id, message_id)

    async def _send_from_params(self, raw_params: Any) -> int:
        raw_arguments = _validate_tool_call(raw_params)
        chat_id = _resolve_chat_id(raw_arguments, self._recipient_chat_ids)
        message = _resolve_message(raw_arguments)
        return await self._send_message(chat_id, message)

    async def _send_message(self, chat_id: str, message: str) -> int:
        client = self._listener.client
        if client is None:
            msg = "Telegram client is not connected"
            raise RuntimeError(msg)
        return await telethon.send_text_message(client, chat_id, message)
