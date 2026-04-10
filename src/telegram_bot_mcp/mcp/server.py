from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, cast

from telegram_bot_mcp.client import TelegramBotListenerClient
from telegram_bot_mcp.config import TelegramBotMCPConfig, load_config
from telegram_bot_mcp.mcp.protocol import JsonDict, Payloads, ServerHelpers
from telegram_bot_mcp.mcp.transport import ProtocolIO
from telegram_bot_mcp.request_parsing import required_text, required_user_id

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
        request_id = request.get("id")
        if request_id is None:
            return None
        try:
            return await self._dispatch_request(request, request_id)
        except Exception as exc:
            logger.error("MCP request failed: %s", exc, exc_info=True)
            return ServerHelpers.jsonrpc_error(request_id, -32000, str(exc))

    async def _dispatch_request(self, request: JsonDict, request_id: Any) -> JsonDict:
        method = request.get("method")
        params = request.get("params", {})
        handler = _simple_handlers().get(str(method))
        if handler is not None:
            return ServerHelpers.jsonrpc_result(request_id, handler())
        if method == "tools/call":
            result = await self.handle_tools_call(
                name=str(params.get("name") or ""),
                arguments=ServerHelpers.request_arguments(params),
            )
            return ServerHelpers.jsonrpc_result(request_id, result)
        return ServerHelpers.jsonrpc_error(request_id, -32601, f"Method not found: {method}")

    async def handle_tools_call(self, name: str, arguments: JsonDict) -> JsonDict:
        handlers = _tool_handlers(self)
        handler = handlers.get(name)
        if handler is None:
            return Payloads.result({"ok": False, "error": f"Unknown tool: {name}"})
        return Payloads.result(await handler(arguments))

    async def _send_message(self, arguments: JsonDict) -> JsonDict:
        return await self.client.send_message(
            telegram_user_id=required_user_id(arguments),
            text=required_text(arguments, field_name="text"),
        )

    async def _send_buttons(self, arguments: JsonDict) -> JsonDict:
        buttons = arguments.get("buttons")
        if not isinstance(buttons, list) or not buttons:
            raise ValueError("buttons is required")
        return await self.client.send_buttons(
            telegram_user_id=required_user_id(arguments),
            text=required_text(arguments, field_name="text"),
            buttons=cast(list[list[dict[str, str]]], buttons),
        )

    async def _create_survey(self, arguments: JsonDict) -> JsonDict:
        questions = arguments.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValueError("questions is required")
        return await self.client.create_survey(
            telegram_user_id=required_user_id(arguments),
            title=required_text(arguments, field_name="title"),
            questions=cast(list[dict[str, Any]], questions),
        )

    async def _get_history(self, arguments: JsonDict) -> JsonDict:
        session_id = str(arguments.get("session_id") or "").strip() or None
        limit = int(arguments.get("limit") or 200)
        return await self.client.get_history(
            telegram_user_id=required_user_id(arguments),
            limit=limit,
            session_id=session_id,
        )


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


def _simple_handlers() -> dict[str, Any]:
    return {
        "initialize": ServerHelpers.initialize_result,
        "resources/list": ServerHelpers.resources_result,
        "resources/templates/list": ServerHelpers.resource_templates_result,
        "tools/list": Payloads.tools_result,
    }


def _tool_handlers(server: TelegramBotMCPServer) -> dict[str, Any]:
    return {
        "send_telegram_bot_message": server._send_message,
        "send_telegram_bot_buttons": server._send_buttons,
        "create_telegram_bot_survey": server._create_survey,
        "get_telegram_bot_history": server._get_history,
    }
