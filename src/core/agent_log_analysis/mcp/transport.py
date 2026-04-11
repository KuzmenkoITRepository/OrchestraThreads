from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol, cast


class MessageReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...

    def readline(self, limit: int = -1, /) -> bytes: ...


def encode_message(payload: dict[str, Any], *, framing: str) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "content_length":
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body
    return b"".join((body, b"\n"))


def decode_json_object(raw_payload: str) -> dict[str, Any]:
    decoded = json.loads(raw_payload)
    if not isinstance(decoded, dict):
        raise RuntimeError("MCP message must be a JSON object")
    return cast(dict[str, Any], decoded)


async def read_message(
    reader: MessageReader,
    *,
    framing_hint: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    if framing_hint == "content_length":
        return await _read_content_length_message(reader), "content_length"
    if framing_hint == "newline":
        return await _read_newline_message(reader), "newline"

    first_byte = await asyncio.to_thread(reader.read, 1)
    if not first_byte:
        return None, None
    if first_byte in b"{[":
        return await _read_newline_message(reader, first_chunk=first_byte), "newline"
    return await _read_content_length_message(reader, first_chunk=first_byte), "content_length"


async def _read_newline_message(
    reader: MessageReader,
    *,
    first_chunk: bytes = b"",
) -> dict[str, Any] | None:
    line = first_chunk + await asyncio.to_thread(reader.readline)
    if not line:
        return None
    return decode_json_object(line.decode("utf-8").strip())


def _parse_content_length(header_bytes: bytes) -> int:
    for raw_line in header_bytes.decode("ascii").split("\r\n"):
        if raw_line.lower().startswith("content-length:"):
            return int(raw_line.split(":", 1)[1].strip())
    raise RuntimeError("Missing Content-Length header")


async def _read_content_length_message(
    reader: MessageReader,
    *,
    first_chunk: bytes = b"",
) -> dict[str, Any] | None:
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
    return decode_json_object(body.decode("utf-8"))
