from __future__ import annotations

from core.orchestra_thread.mcp_tools_common import JSON_MAP

JSONRPC_FIELD = "jsonrpc"
JSONRPC_VERSION = "2.0"
REQUEST_ID_FIELD = "id"
RESULT_FIELD = "result"
ERROR_FIELD = "error"
ERROR_MESSAGE_FIELD = "message"
METHOD_NOT_FOUND_CODE = -32601
INTERNAL_ERROR_CODE = -32000


def method_response(request_id: object, result_payload: JSON_MAP) -> JSON_MAP:
    return {
        JSONRPC_FIELD: JSONRPC_VERSION,
        REQUEST_ID_FIELD: request_id,
        RESULT_FIELD: result_payload,
    }


def error_response(request_id: object, code: int, message: str) -> JSON_MAP:
    return {
        JSONRPC_FIELD: JSONRPC_VERSION,
        REQUEST_ID_FIELD: request_id,
        ERROR_FIELD: {"code": code, ERROR_MESSAGE_FIELD: message},
    }
