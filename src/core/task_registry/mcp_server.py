from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, cast

logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "task-registry"


class TaskRegistryMCPServer:
    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"},
            }

        request_id = request.get("id")
        method = request.get("method")

        if not isinstance(method, str) or not method:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "error": {"code": -32600, "message": "Invalid Request"},
            }

        try:
            return self._dispatch_request(request_id, method)
        except Exception:
            logger.exception("Request handling failed")
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "error": {"code": -32000, "message": "Internal error"},
            }

    async def serve(self) -> None:
        while True:
            try:
                request = await self._read_request()
            except json.JSONDecodeError as exc:
                logger.error("Invalid JSON received: %s", exc)
                await self._write_response(
                    {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                )
                continue

            if request is None:
                return

            response = await self.handle_request(request)
            if response is not None:
                await self._write_response(response)

    def _dispatch_request(self, request_id: Any, method: str) -> dict[str, Any] | None:
        if method == "initialize":
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
                },
            }
        if method == "tools/list":
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": {"tools": []},
            }
        if request_id is None:
            return None
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async def _read_request(self) -> dict[str, Any] | None:
        raw_line = await asyncio.to_thread(sys.stdin.buffer.readline)
        if not raw_line:
            return None

        text = raw_line.decode("utf-8").strip()
        if not text:
            return None

        return cast(dict[str, Any] | None, json.loads(text))

    async def _write_response(self, payload: dict[str, Any]) -> None:
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
        asyncio.run(TaskRegistryMCPServer().serve())
    except KeyboardInterrupt:
        logger.info("Task registry MCP server stopped")


if __name__ == "__main__":
    main()
