from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, cast

from core.docker_mcp.mcp_tool_specs import tool_specs
from core.docker_mcp.mcp_tools import DockerMCPTools

logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "docker-mcp"

JsonDict = dict[str, Any]


def _jsonrpc_result(request_id: Any, result_payload: JsonDict) -> JsonDict:  # noqa: ANN401
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result_payload}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> JsonDict:  # noqa: ANN401
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _request_arguments(params: Any) -> JsonDict:  # noqa: ANN401
    arguments = params.get("arguments") if isinstance(params, dict) else None
    return dict(arguments) if isinstance(arguments, dict) else {}


class DockerMCPServer:
    def __init__(self) -> None:
        self._tools = DockerMCPTools()

    async def handle_request(self, request: JsonDict) -> JsonDict | None:
        if not isinstance(request, dict):
            return _jsonrpc_error(None, -32600, "Invalid Request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str) or not method:
            return _jsonrpc_error(request_id, -32600, "Invalid Request")
        try:
            return await self._dispatch_request(request_id, method, request.get("params", {}))
        except Exception:
            logger.exception("Docker MCP request handling failed")
            return _jsonrpc_error(request_id, -32000, "Internal error")

    async def serve(self) -> None:
        while True:
            try:
                request = await self._read_request()
            except json.JSONDecodeError as exc:
                logger.error("Invalid JSON received: %s", exc)
                await self._write_response(_jsonrpc_error(None, -32700, "Parse error"))
                continue
            if request is None:
                return
            response = await self.handle_request(request)
            if response is not None:
                await self._write_response(response)

    async def _dispatch_request(  # noqa: WPS212
        self,
        request_id: Any,  # noqa: ANN401
        method: str,
        params: Any,  # noqa: ANN401
    ) -> JsonDict | None:
        if method == "initialize":
            return _jsonrpc_result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
                },
            )
        if method == "tools/list":
            return _jsonrpc_result(request_id, {"tools": tool_specs()})
        if method == "tools/call":
            tool_name = self._extract_tool_name(params)
            arguments = _request_arguments(params)
            tool_result = self._tools.dispatch(tool_name, arguments)
            return _jsonrpc_result(request_id, tool_result)
        if request_id is None:
            return None
        return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _extract_tool_name(params: Any) -> str:  # noqa: ANN401
        raw_name = params.get("name") if isinstance(params, dict) else None
        return str(raw_name or "")

    async def _read_request(self) -> JsonDict | None:
        raw_line = await asyncio.to_thread(sys.stdin.buffer.readline)
        if not raw_line:
            return None
        text = raw_line.decode("utf-8").strip()
        if not text:
            return None
        return cast(JsonDict | None, json.loads(text))

    async def _write_response(self, payload: JsonDict) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        await asyncio.to_thread(sys.stdout.write, f"{body}\n")
        await asyncio.to_thread(sys.stdout.flush)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        asyncio.run(DockerMCPServer().serve())
    except KeyboardInterrupt:
        logger.info("Docker MCP server stopped")


if __name__ == "__main__":
    main()
