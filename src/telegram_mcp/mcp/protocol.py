"""JSON-RPC envelope builders and MCP content wrappers."""

from __future__ import annotations

import json
from typing import Any

JsonDict = dict[str, Any]

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "telegram-mcp"
_SERVER_VERSION = "0.3.0"


def jsonrpc_result(request_id: object, result_payload: JsonDict) -> JsonDict:
    """Wrap a result payload in a JSON-RPC response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result_payload}


def jsonrpc_error(request_id: object, code: int, message: str) -> JsonDict:
    """Wrap an error in a JSON-RPC response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def initialize_result() -> JsonDict:
    """Build the MCP initialize response."""
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "capabilities": {"tools": {}, "resources": {}},
        "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
    }


def mcp_content(payload: JsonDict) -> JsonDict:
    """Wrap a tool result in MCP structured content format."""
    rendered = json.dumps(payload, ensure_ascii=False)
    return {
        "structuredContent": payload,
        "content": [{"type": "text", "text": rendered}],
    }
