from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, cast

from core.task_registry.mcp_tool_payloads import JsonDict

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "task-registry"
INVALID_REQUEST_CODE = -32600
INTERNAL_ERROR_CODE = -32000
PARSE_ERROR_CODE = -32700
METHOD_NOT_FOUND_CODE = -32601


def jsonrpc_result(request_id: Any, result_payload: JsonDict) -> JsonDict:  # noqa: ANN401
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result_payload}


def jsonrpc_error(request_id: Any, code: int, message: str) -> JsonDict:  # noqa: ANN401
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def request_arguments(request_params: Any) -> JsonDict:  # noqa: ANN401
    arguments = request_params.get("arguments") if isinstance(request_params, dict) else None
    return dict(arguments) if isinstance(arguments, dict) else {}


def extract_tool_name(request_params: Any) -> str:  # noqa: ANN401
    raw_name = request_params.get("name") if isinstance(request_params, dict) else None
    return str(raw_name or "")


async def read_request() -> JsonDict | None:
    raw_line = await asyncio.to_thread(sys.stdin.buffer.readline)
    if not raw_line:
        return None

    text = raw_line.decode("utf-8").strip()
    if not text:
        return None

    return cast(JsonDict | None, json.loads(text))


async def write_response(payload: JsonDict) -> None:
    body = json.dumps(payload, ensure_ascii=False)
    await asyncio.to_thread(sys.stdout.write, f"{body}\n")
    await asyncio.to_thread(sys.stdout.flush)
