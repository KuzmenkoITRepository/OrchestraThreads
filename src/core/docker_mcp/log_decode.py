from __future__ import annotations

import json
import subprocess
from typing import Any


def command_output(result: subprocess.CompletedProcess[str]) -> str:
    stdout = str(result.stdout or "")
    stderr = str(result.stderr or "")
    return "".join((stdout, stderr)).strip()


def bytes_output(result: subprocess.CompletedProcess[bytes]) -> str:
    stdout = bytes(result.stdout or b"")
    stderr = bytes(result.stderr or b"")
    return b"".join((stdout, stderr)).decode("utf-8", errors="replace").strip()


def containers_payload(stdout: str) -> list[dict[str, Any]]:
    payload = json.loads(stdout or "[]")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def decode_logs_output(raw_output: bytes) -> str:
    if not raw_output:
        return ""
    if _looks_like_raw_stream(raw_output):
        return _decode_raw_stream(raw_output)
    return raw_output.decode("utf-8", errors="replace").strip()


def _looks_like_raw_stream(raw_output: bytes) -> bool:
    if len(raw_output) < 8:
        return False
    stream_type = raw_output[0]
    return stream_type in {1, 2} and raw_output[1:4] == b"\x00\x00\x00"


def _decode_raw_stream(raw_output: bytes) -> str:
    chunks: list[str] = []
    cursor = 0
    while cursor + 8 <= len(raw_output):
        cursor = _read_frame(raw_output, cursor, chunks)
    if cursor < len(raw_output):
        chunks.append(raw_output[cursor:].decode("utf-8", errors="replace"))
    return "".join(chunks).strip()


def _read_frame(raw_output: bytes, cursor: int, chunks: list[str]) -> int:
    header_end = cursor + 8
    frame_bytes = raw_output[cursor + 4 : header_end]
    frame_size = int.from_bytes(frame_bytes, byteorder="big")
    chunk = raw_output[header_end : header_end + frame_size]
    chunks.append(chunk.decode("utf-8", errors="replace"))
    return header_end + frame_size
