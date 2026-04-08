"""MCP stdio protocol IO framing: content-length and newline-delimited."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from telegram_mcp.mcp_protocol import JsonDict


def encode_message(payload: JsonDict, *, framing: str) -> bytes:
    """Encode a JSON-RPC payload with the given framing style."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "content_length":
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body
    return b"".join((body, b"\n"))


async def read_message(
    reader: Any,
    *,
    framing_hint: str | None = None,
) -> tuple[JsonDict | None, str | None]:
    """Read one JSON-RPC message from the reader, auto-detecting framing."""
    if framing_hint == "content_length":
        return await _read_content_length(reader), "content_length"
    if framing_hint == "newline":
        return await _read_newline(reader), "newline"
    return await _read_auto_detect(reader)


async def _read_auto_detect(reader: Any) -> tuple[JsonDict | None, str | None]:
    first_byte = await asyncio.to_thread(reader.read, 1)
    if not first_byte:
        return None, None
    if first_byte in b"{[":
        msg = await _read_newline(reader, first_chunk=first_byte)
        return msg, "newline"
    msg = await _read_content_length(reader, first_chunk=first_byte)
    return msg, "content_length"


async def _read_newline(
    reader: Any,
    *,
    first_chunk: bytes = b"",
) -> JsonDict | None:
    line = first_chunk + await asyncio.to_thread(reader.readline)
    if not line:
        return None
    return cast(JsonDict, json.loads(line.decode("utf-8").strip()))


async def _read_content_length(
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
    content_length = _parse_content_length(header_bytes)
    body = await asyncio.to_thread(reader.read, content_length)
    if not body:
        return None
    return cast(JsonDict, json.loads(body.decode("utf-8")))


def _parse_content_length(header_bytes: bytes) -> int:
    for raw_line in header_bytes.decode("ascii").split("\r\n"):
        if raw_line.lower().startswith("content-length:"):
            return int(raw_line.split(":", 1)[1].strip())
    raise RuntimeError("Missing Content-Length header")
