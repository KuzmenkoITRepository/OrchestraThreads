"""Thin MCP server dispatcher for Telegram messaging."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from telegram_mcp import (
    batch_send_handler,
    chat_info,
    edit_delete_handlers,
    message_store,
    receipt_state,
    send_dispatch,
)
from telegram_mcp.config import TelegramMCPConfig, load_config
from telegram_mcp.mcp_protocol import (
    JsonDict,
    Payloads,
    ServerHelpers,
    ensure_text,
    normalize_optional_str,
)
from telegram_mcp.mcp_transport import encode_message, read_message
from telegram_mcp.rate_limit_state import RateLimitState
from telegram_mcp.recipient_registry import RecipientRegistry, load_recipients_from_env
from telegram_mcp.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramMCPServer:
    """MCP server: dispatches JSON-RPC requests to tools and resources."""

    def __init__(
        self,
        *,
        config: TelegramMCPConfig | None = None,
        registry: RecipientRegistry | None = None,
        store: message_store.MessageStore | None = None,
    ) -> None:
        self.config = config or load_config()
        self.registry = registry or load_recipients_from_env()
        self.rate_limits = RateLimitState()
        self.chat_cache = chat_info.ChatInfoCache()
        self.store = store or message_store.MessageStore(message_store.default_db_path())
        self.client = TelegramClient(
            api_id=self.config.auth.api_id,
            api_hash=self.config.auth.api_hash,
            session_string=self.config.auth.session_string,
            max_retries=self.config.defaults.max_retries,
            timeout_seconds=self.config.defaults.timeout_seconds,
        )
        self._client_started = False

    async def close(self) -> None:
        """Shut down the Telegram client and store."""
        await self.client.close()
        self.store.close()
        self._client_started = False

    async def handle_request(self, request: JsonDict) -> JsonDict | None:
        """Route a single JSON-RPC request to the correct handler."""
        request_id = request.get("id")
        if request_id is None:
            return None
        try:
            return await self._dispatch(request, request_id)
        except Exception as exc:
            logger.error("MCP request failed: %s", exc, exc_info=True)
            return ServerHelpers.jsonrpc_error(request_id, -32000, str(exc))

    async def handle_tools_call(self, name: str, arguments: JsonDict) -> JsonDict:
        """Dispatch a tools/call by name."""
        if name == "send_telegram_message":
            return await _handle_send(self, arguments)
        if name == "send_telegram_message_batch":
            return await batch_send_handler.handle_batch_send(
                lambda args: _handle_send(self, args),
                arguments,
            )
        if name == "upsert_recipient":
            alias = ensure_text(arguments.get("alias"), field_name="alias")
            raw_cid = arguments.get("chat_id")
            if raw_cid is None or str(raw_cid).strip() == "":
                raise RuntimeError("chat_id is required and must be a non-zero integer")
            self.registry.register(alias, int(raw_cid))
            return Payloads.result({"ok": True, "recipients": self.registry.list_entries()})
        if name == "remove_recipient":
            removed = self.registry.unregister(
                ensure_text(arguments.get("alias"), field_name="alias")
            )
            return Payloads.result({"ok": True, "removed": removed})
        raw = await self.client.require_client()
        return await _dispatch_raw_tool(self, name, arguments, raw)

    async def handle_resource_read(self, uri: str) -> JsonDict:
        """Read a resource by URI."""
        if uri.startswith("telegram://thread/") or uri.startswith("telegram://chat/"):
            return await _read_template_resource(self, uri)
        if uri == "telegram://recipients":
            return Payloads.result({"ok": True, "recipients": self.registry.list_entries()})
        if uri == "telegram://rate_limits":
            return Payloads.result({"ok": True, **self.rate_limits.snapshot()})
        return Payloads.result({"ok": False, "error": f"Unknown resource: {uri}"})

    async def ensure_client_started(self) -> None:
        """Start the Telegram client if not already started."""
        if self._client_started:
            return
        await self.client.start()
        self._client_started = True

    async def _dispatch(self, request: JsonDict, request_id: object) -> JsonDict:
        method = request.get("method")
        params = request.get("params", {})
        simple = {
            "initialize": ServerHelpers.initialize_result,
            "resources/list": Payloads.resources_result,
            "resources/templates/list": Payloads.resource_templates_result,
            "tools/list": Payloads.tools_result,
        }
        handler = simple.get(str(method))
        if handler is not None:
            return ServerHelpers.jsonrpc_result(request_id, handler())
        safe_params = params if isinstance(params, dict) else {}
        if method == "tools/call":
            return ServerHelpers.jsonrpc_result(
                request_id,
                await self.handle_tools_call(
                    name=str(safe_params.get("name") or ""),
                    arguments=ServerHelpers.request_arguments(safe_params),
                ),
            )
        if method == "resources/read":
            return ServerHelpers.jsonrpc_result(
                request_id,
                await self.handle_resource_read(str(safe_params.get("uri") or "")),
            )
        return ServerHelpers.jsonrpc_error(
            request_id,
            -32601,
            f"Method not found: {method}",
        )


async def _read_template_resource(server: TelegramMCPServer, uri: str) -> JsonDict:
    """Handle parameterized resource URIs."""
    if uri.endswith("/messages"):
        thread_id = uri.removeprefix("telegram://thread/").removesuffix("/messages")
        records = server.store.list_by_thread(thread_id)
        return Payloads.result(
            {"ok": True, "thread_id": thread_id, "messages": [r.to_dict() for r in records]}
        )
    chat_id = server.registry.resolve(
        uri.removeprefix("telegram://chat/").removesuffix("/info") or None,
    )
    cached = server.chat_cache.get(chat_id)
    if cached is None:
        raw = await server.client.require_client()
        cached = await chat_info.fetch_chat_info(raw, chat_id)
        server.chat_cache.put(cached)
    return Payloads.result({"ok": True, **cached.to_dict()})


async def _dispatch_raw_tool(
    server: TelegramMCPServer,
    name: str,
    arguments: JsonDict,
    raw_client: object,
) -> JsonDict:
    """Route tools that need the raw Telethon client."""
    chat_id = server.registry.resolve(normalize_optional_str(arguments.get("recipient")))
    if name == "edit_telegram_message":
        msg_id, new_text = edit_delete_handlers.parse_edit_args(arguments)
        return await edit_delete_handlers.handle_edit(
            raw_client,
            server.store,
            chat_id,
            msg_id,
            new_text,
        )
    if name == "delete_telegram_message":
        msg_id = edit_delete_handlers.parse_delete_args(arguments)
        return await edit_delete_handlers.handle_delete(
            raw_client,
            server.store,
            chat_id,
            msg_id,
        )
    if name == "get_telegram_chat_info":
        cached = server.chat_cache.get(chat_id)
        if cached is None:
            cached = await chat_info.fetch_chat_info(raw_client, chat_id)
            server.chat_cache.put(cached)
        return Payloads.result({"ok": True, **cached.to_dict()})
    if name == "check_telegram_read_receipt":
        if arguments.get("message_id") is None:
            raise RuntimeError("message_id is required")
        hint = await receipt_state.check_read_receipt(
            raw_client,
            chat_id,
            int(arguments["message_id"]),
        )
        return Payloads.result({"ok": True, **hint.to_dict()})
    return Payloads.result({"ok": False, "error": f"Unknown tool: {name}"})


async def _handle_send(server: TelegramMCPServer, arguments: JsonDict) -> JsonDict:
    message = ensure_text(arguments.get("message"), field_name="message")
    recipient = normalize_optional_str(arguments.get("recipient"))
    chat_id = server.registry.resolve(recipient)
    server.rate_limits.record_request()
    await server.ensure_client_started()
    send_result = await _try_send(server, chat_id, message, arguments)
    alias = recipient or server.registry.default_alias
    if not send_result.get("ok"):
        return Payloads.result(
            {
                "ok": False,
                "error": str(send_result.get("error") or "Telegram send failed"),
                "error_code": int(send_result.get("error_code") or 500),
                "chat_id": chat_id,
                "recipient": alias,
            }
        )
    server.store.record_send(
        message_store.SendInput(
            telegram_message_id=int(send_result.get("message_id") or 0),
            chat_id=chat_id,
            recipient_alias=alias,
            text=message,
            parse_mode=str(arguments.get("parse_mode") or "").strip() or None,
            reply_to_message_id=int(arguments["reply_to_message_id"])
            if arguments.get("reply_to_message_id")
            else None,
            thread_id=normalize_optional_str(arguments.get("thread_id")),
        )
    )
    return Payloads.result(
        {
            "ok": True,
            "message_id": int(send_result.get("message_id") or 0),
            "chat_id": chat_id,
            "recipient": alias,
        }
    )


async def _try_send(
    server: TelegramMCPServer,
    chat_id: int,
    message: str,
    arguments: JsonDict,
) -> JsonDict:
    """Execute text or rich send, catching errors into a result dict."""
    request = send_dispatch.parse_send_request(arguments, message)
    if send_dispatch.is_rich_request(request):
        coro = server.client.send_rich(
            chat_id,
            request,
            on_flood_wait=server.rate_limits.record_flood_wait,
        )
    else:
        coro = server.client.send_message(chat_id, message)
    try:
        return await coro
    except Exception as exc:
        logger.error("Telegram tool failed: %s", exc, exc_info=True)
        return {"ok": False, "message_id": 0, "error": str(exc)}


def main() -> None:
    """Entry point for the telegram-mcp MCP server."""
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_main_async())


async def _main_async() -> None:
    server = TelegramMCPServer()
    framing: str | None = None
    try:  # noqa: WPS501 - runtime must always close the MCP client on exit.
        while True:
            request, framing = await read_message(
                sys.stdin.buffer,
                framing_hint=framing,
            )
            if request is None:
                break
            response = await server.handle_request(request)
            if response is None:
                continue
            sys.stdout.buffer.write(encode_message(response, framing=framing or "newline"))
            sys.stdout.buffer.flush()
    finally:
        await server.close()


if __name__ == "__main__":
    main()
