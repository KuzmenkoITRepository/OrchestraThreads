from __future__ import annotations

# pyright: reportMissingImports=false

import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional

from .config import TelegramMCPConfig
from .telegram_client import TelegramClient


logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"


def _normalize_optional_str(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return normalized


class TelegramMCPServer:
    def __init__(
        self,
        *,
        config: Optional[TelegramMCPConfig] = None,
    ) -> None:
        self.config = config or TelegramMCPConfig()
        self.client = TelegramClient(
            api_id=self.config.api_id,
            api_hash=self.config.api_hash,
            session_string=self.config.session_string,
        )
        self._client_started = False

    async def _ensure_client_started(self) -> None:
        if self._client_started:
            return
        await self.client.start()
        self._client_started = True

    async def close(self) -> None:
        await self.client.close()
        self._client_started = False

    @staticmethod
    def _tool(
        name: str, description: str, input_schema: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }

    def _result(
        self, payload: dict[str, Any], *, text: Optional[str] = None
    ) -> dict[str, Any]:
        return {
            "structuredContent": payload,
            "content": [
                {
                    "type": "text",
                    "text": text or json.dumps(payload, ensure_ascii=False),
                }
            ],
        }

    def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "telegram-mcp",
                "version": "0.1.0",
            },
        }

    def handle_tools_list(self) -> dict[str, Any]:
        return {
            "tools": [
                self._tool(
                    "send_telegram_message",
                    "Send a Telegram message to a configured recipient alias.",
                    {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "recipient": {"type": "string"},
                        },
                        "required": ["message"],
                    },
                )
            ]
        }

    async def handle_tools_call(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if name == "send_telegram_message":
            return await self._handle_send_telegram_message(arguments)
        return self._result({"ok": False, "error": f"Unknown tool: {name}"})

    async def _handle_send_telegram_message(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            await self._ensure_client_started()
            message = _ensure_text(arguments.get("message"), field_name="message")
            recipient = _normalize_optional_str(arguments.get("recipient"))
            chat_id = self.config.resolve_chat_id(recipient)
            send_result = await self.client.send_message(
                chat_id,
                message,
            )
            if not send_result.get("ok"):
                return self._result(
                    {
                        "ok": False,
                        "error": str(
                            send_result.get("error") or "Telegram send failed"
                        ),
                        "error_code": int(send_result.get("error_code") or 500),
                        "chat_id": chat_id,
                        "recipient": recipient or self.config.default_recipient,
                    }
                )

            message_id = int(send_result.get("message_id") or 0)
            resolved_recipient = recipient or self.config.default_recipient
            return self._result(
                {
                    "ok": True,
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "recipient": resolved_recipient,
                }
            )
        except Exception as exc:
            logger.error("Telegram tool failed: %s", exc, exc_info=True)
            return self._result({"ok": False, "error": str(exc)})

    async def handle_request(self, request: dict[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})
        if request_id is None:
            return None
        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": self.handle_initialize(params),
                }
            if method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": self.handle_tools_list(),
                }
            if method == "tools/call":
                result = await self.handle_tools_call(
                    name=str(params.get("name") or ""),
                    arguments=params.get("arguments")
                    if isinstance(params.get("arguments"), dict)
                    else {},
                )
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        except Exception as exc:
            logger.error("MCP request failed: %s", exc, exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }


def _encode_message(payload: dict[str, Any], *, framing: str) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "content_length":
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body
    return body + b"\n"


async def _read_message(
    reader,
    *,
    framing_hint: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if framing_hint == "content_length":
        return await _read_content_length_message(reader), "content_length"
    if framing_hint == "newline":
        return await _read_newline_message(reader), "newline"

    first_byte = await asyncio.to_thread(reader.read, 1)
    if not first_byte:
        return None, None
    if first_byte in b"{[":
        return await _read_newline_message(reader, first_chunk=first_byte), "newline"
    return await _read_content_length_message(
        reader, first_chunk=first_byte
    ), "content_length"


async def _read_newline_message(
    reader, *, first_chunk: bytes = b""
) -> Optional[dict[str, Any]]:
    line = first_chunk + await asyncio.to_thread(reader.readline)
    if not line:
        return None
    return json.loads(line.decode("utf-8").strip())


async def _read_content_length_message(
    reader, *, first_chunk: bytes = b""
) -> Optional[dict[str, Any]]:
    header_bytes = bytes(first_chunk)
    while True:
        chunk = await asyncio.to_thread(reader.read, 1)
        if not chunk:
            return None
        header_bytes += chunk
        if header_bytes.endswith(b"\r\n\r\n"):
            break
    content_length = None
    for raw_line in header_bytes.decode("ascii").split("\r\n"):
        if raw_line.lower().startswith("content-length:"):
            content_length = int(raw_line.split(":", 1)[1].strip())
            break
    if content_length is None:
        raise RuntimeError("Missing Content-Length header")
    body = await asyncio.to_thread(reader.read, content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


async def main_async() -> None:
    server = TelegramMCPServer()
    framing: Optional[str] = None
    try:
        while True:
            request, framing = await _read_message(
                sys.stdin.buffer, framing_hint=framing
            )
            if request is None:
                break
            response = await server.handle_request(request)
            if response is not None:
                sys.stdout.buffer.write(
                    _encode_message(response, framing=framing or "newline")
                )
                sys.stdout.buffer.flush()
    finally:
        await server.close()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
