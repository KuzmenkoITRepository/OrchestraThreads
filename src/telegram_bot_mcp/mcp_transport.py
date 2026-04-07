from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from telegram_bot_mcp.mcp_protocol import JsonDict


class ProtocolIO:
    @staticmethod
    def encode_message(payload: JsonDict, *, framing: str) -> bytes:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if framing == "content_length":
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            return header + body
        return b"".join((body, b"\n"))

    @staticmethod
    async def read_message(
        reader: Any, *, framing_hint: str | None = None
    ) -> tuple[JsonDict | None, str | None]:
        if framing_hint == "content_length":
            return await ProtocolIO._read_content_length_message(reader), "content_length"
        if framing_hint == "newline":
            return await ProtocolIO._read_newline_message(reader), "newline"
        first_byte = await asyncio.to_thread(reader.read, 1)
        if not first_byte:
            return None, None
        if first_byte in b"{[":
            return await ProtocolIO._read_newline_message(reader, first_chunk=first_byte), "newline"
        return (
            await ProtocolIO._read_content_length_message(reader, first_chunk=first_byte),
            "content_length",
        )

    @staticmethod
    async def _read_newline_message(reader: Any, *, first_chunk: bytes = b"") -> JsonDict | None:
        line = first_chunk + await asyncio.to_thread(reader.readline)
        if not line:
            return None
        return cast(JsonDict, json.loads(line.decode("utf-8").strip()))

    @staticmethod
    async def _read_content_length_message(
        reader: Any, *, first_chunk: bytes = b""
    ) -> JsonDict | None:
        header_bytes = bytes(first_chunk)
        while not header_bytes.endswith(b"\r\n\r\n"):
            chunk = await asyncio.to_thread(reader.read, 1)
            if not chunk:
                return None
            header_bytes += chunk
        content_length = ProtocolIO._content_length(header_bytes)
        body = await asyncio.to_thread(reader.read, content_length)
        if not body:
            return None
        return cast(JsonDict, json.loads(body.decode("utf-8")))

    @staticmethod
    def _content_length(header_bytes: bytes) -> int:
        for raw_line in header_bytes.decode("ascii").split("\r\n"):
            if raw_line.lower().startswith("content-length:"):
                return int(raw_line.split(":", 1)[1].strip())
        raise RuntimeError("Missing Content-Length header")
