from __future__ import annotations

# pyright: reportMissingImports=false
import asyncio
import json
import logging
import os
import sys
from typing import Any, cast

from telegram_mcp.config import TelegramMCPConfig, load_config
from telegram_mcp.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"

JsonDict = dict[str, Any]


class _ServerHelpers:
    @staticmethod
    def jsonrpc_result(request_id: Any, result: JsonDict) -> JsonDict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def jsonrpc_error(request_id: Any, code: int, message: str) -> JsonDict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def initialize_result() -> JsonDict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "telegram-mcp", "version": "0.1.0"},
        }

    @staticmethod
    def resources_result() -> JsonDict:
        return {"resources": []}

    @staticmethod
    def resource_templates_result() -> JsonDict:
        return {"resourceTemplates": []}

    @staticmethod
    def request_arguments(params: Any) -> JsonDict:
        arguments = params.get("arguments") if isinstance(params, dict) else None
        if isinstance(arguments, dict):
            return arguments
        return {}

    @staticmethod
    async def send_tool_message(
        ensure_client_started: Any,
        client: TelegramClient,
        *,
        chat_id: int,
        message: str,
    ) -> JsonDict:
        await ensure_client_started()
        return await client.send_message(chat_id, message)


class _ProtocolPayloads:
    @staticmethod
    def normalize_optional_str(value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def ensure_text(value: Any, *, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise RuntimeError(f"{field_name} is required")
        return normalized

    @staticmethod
    def tool(name: str, description: str, input_schema: JsonDict) -> JsonDict:
        return {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }

    @staticmethod
    def result(payload: JsonDict, *, text: str | None = None) -> JsonDict:
        rendered_text = text or json.dumps(payload, ensure_ascii=False)
        return {
            "structuredContent": payload,
            "content": [{"type": "text", "text": rendered_text}],
        }

    @staticmethod
    def tools_result() -> JsonDict:
        tool_schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}, "recipient": {"type": "string"}},
            "required": ["message"],
        }
        return {
            "tools": [
                _ProtocolPayloads.tool(
                    "send_telegram_message",
                    "Send a Telegram message to a configured recipient alias.",
                    tool_schema,
                )
            ]
        }

    @staticmethod
    def send_failure_result(
        send_result: JsonDict,
        *,
        chat_id: int,
        recipient: str | None,
        default_recipient: str,
    ) -> JsonDict:
        return _ProtocolPayloads.result(
            {
                "ok": False,
                "error": str(send_result.get("error") or "Telegram send failed"),
                "error_code": int(send_result.get("error_code") or 500),
                "chat_id": chat_id,
                "recipient": recipient or default_recipient,
            }
        )

    @staticmethod
    def send_success_result(
        send_result: JsonDict,
        *,
        chat_id: int,
        recipient: str | None,
        default_recipient: str,
    ) -> JsonDict:
        return _ProtocolPayloads.result(
            {
                "ok": True,
                "message_id": int(send_result.get("message_id") or 0),
                "chat_id": chat_id,
                "recipient": recipient or default_recipient,
            }
        )


class _ProtocolIO:
    @staticmethod
    def encode_message(payload: JsonDict, *, framing: str) -> bytes:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if framing == "content_length":
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            return header + body
        return b"".join((body, b"\n"))

    @staticmethod
    async def read_message(
        reader: Any,
        *,
        framing_hint: str | None = None,
    ) -> tuple[JsonDict | None, str | None]:
        if framing_hint == "content_length":
            return await _ProtocolIO._read_content_length_message(reader), "content_length"
        if framing_hint == "newline":
            return await _ProtocolIO._read_newline_message(reader), "newline"

        first_byte = await asyncio.to_thread(reader.read, 1)
        if not first_byte:
            return None, None
        if first_byte in b"{[":
            return await _ProtocolIO._read_newline_message(
                reader, first_chunk=first_byte
            ), "newline"
        return (
            await _ProtocolIO._read_content_length_message(reader, first_chunk=first_byte),
            "content_length",
        )

    @staticmethod
    async def _read_newline_message(
        reader: Any,
        *,
        first_chunk: bytes = b"",
    ) -> JsonDict | None:
        line = first_chunk + await asyncio.to_thread(reader.readline)
        if not line:
            return None
        decoded_line = line.decode("utf-8").strip()
        return cast(JsonDict, json.loads(decoded_line))

    @staticmethod
    async def _read_content_length_message(
        reader: Any,
        *,
        first_chunk: bytes = b"",
    ) -> JsonDict | None:
        header_bytes = bytes(first_chunk)
        while not header_bytes.endswith(b"\r\n\r\n"):
            chunk = await asyncio.to_thread(reader.read, 1)
            if not chunk:
                return None
            header_bytes += chunk
        content_length = _ProtocolIO._content_length(header_bytes)
        body = await asyncio.to_thread(reader.read, content_length)
        if not body:
            return None
        decoded_body = body.decode("utf-8")
        return cast(JsonDict, json.loads(decoded_body))

    @staticmethod
    def _content_length(header_bytes: bytes) -> int:
        for raw_line in header_bytes.decode("ascii").split("\r\n"):
            if raw_line.lower().startswith("content-length:"):
                return int(raw_line.split(":", 1)[1].strip())
        raise RuntimeError("Missing Content-Length header")


class TelegramMCPServer:
    def __init__(self, *, config: TelegramMCPConfig | None = None) -> None:
        self.config = config or load_config()
        self.client = TelegramClient(
            api_id=self.config.auth.api_id,
            api_hash=self.config.auth.api_hash,
            session_string=self.config.auth.session_string,
        )
        self._client_started = False

    async def close(self) -> None:
        await self.client.close()
        self._client_started = False

    async def handle_request(self, request: JsonDict) -> JsonDict | None:
        request_id = request.get("id")
        if request_id is None:
            return None
        try:
            return await self._dispatch_request(request, request_id)
        except Exception as exc:
            logger.error("MCP request failed: %s", exc, exc_info=True)
            return _ServerHelpers.jsonrpc_error(request_id, -32000, str(exc))

    async def handle_tools_call(self, name: str, arguments: JsonDict) -> JsonDict:
        if name == "send_telegram_message":
            return await self._handle_send_telegram_message(arguments)
        return _ProtocolPayloads.result({"ok": False, "error": f"Unknown tool: {name}"})

    async def _handle_send_telegram_message(self, arguments: JsonDict) -> JsonDict:
        message = _ProtocolPayloads.ensure_text(arguments.get("message"), field_name="message")
        recipient = _ProtocolPayloads.normalize_optional_str(arguments.get("recipient"))
        chat_id = self.config.resolve_chat_id(recipient)
        try:
            send_result = await _ServerHelpers.send_tool_message(
                self._ensure_client_started,
                self.client,
                chat_id=chat_id,
                message=message,
            )
        except Exception as exc:
            logger.error("Telegram tool failed: %s", exc, exc_info=True)
            return _ProtocolPayloads.result({"ok": False, "error": str(exc)})

        default_recipient = self.config.defaults.default_recipient
        if not send_result.get("ok"):
            return _ProtocolPayloads.send_failure_result(
                send_result,
                chat_id=chat_id,
                recipient=recipient,
                default_recipient=default_recipient,
            )
        return _ProtocolPayloads.send_success_result(
            send_result,
            chat_id=chat_id,
            recipient=recipient,
            default_recipient=default_recipient,
        )

    async def _dispatch_request(self, request: JsonDict, request_id: Any) -> JsonDict:
        method = request.get("method")
        params = request.get("params", {})
        simple_handlers = {
            "initialize": _ServerHelpers.initialize_result,
            "resources/list": _ServerHelpers.resources_result,
            "resources/templates/list": _ServerHelpers.resource_templates_result,
            "tools/list": _ProtocolPayloads.tools_result,
        }
        handler = simple_handlers.get(str(method))
        if handler is not None:
            return _ServerHelpers.jsonrpc_result(request_id, handler())
        if method == "tools/call":
            result = await self.handle_tools_call(
                name=str(params.get("name") or ""),
                arguments=_ServerHelpers.request_arguments(params),
            )
            return _ServerHelpers.jsonrpc_result(request_id, result)
        return _ServerHelpers.jsonrpc_error(request_id, -32601, f"Method not found: {method}")

    async def _ensure_client_started(self) -> None:
        if self._client_started:
            return
        await self.client.start()
        self._client_started = True


class _ServerRuntime:
    @staticmethod
    async def main_async() -> None:
        server = TelegramMCPServer()
        framing: str | None = None
        try:
            while True:
                request, framing = await _ProtocolIO.read_message(
                    sys.stdin.buffer,
                    framing_hint=framing,
                )
                if request is None:
                    break
                response = await server.handle_request(request)
                if response is None:
                    continue
                payload = _ProtocolIO.encode_message(response, framing=framing or "newline")
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
        finally:
            await server.close()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_ServerRuntime.main_async())


if __name__ == "__main__":
    main()
