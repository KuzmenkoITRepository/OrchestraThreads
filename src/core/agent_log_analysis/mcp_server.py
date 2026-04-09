"""MCP server for agent-log-analysis event query tools."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Protocol

from core.agent_log_analysis.mcp_protocol import (
    INVALID_REQUEST_CODE,
    PROTOCOL_VERSION,
    MCPProtocol,
    list_tools,
)
from core.agent_log_analysis.service_runtime import AgentLogAnalysisService
from core.orchestra_thread.mcp_transport import encode_message, read_message

logger = logging.getLogger(__name__)


class _RuntimeProtocol(Protocol):
    async def get_event(self, event_id: str) -> dict[str, object]: ...

    async def query_agent_events(self, payload: object) -> dict[str, object]: ...

    async def get_agent_timeline(self, payload: object) -> dict[str, object]: ...

    async def get_agent_correlation_chain(self, payload: object) -> dict[str, object]: ...

    async def aggregate_agent_events(self, payload: object) -> dict[str, object]: ...

    async def get_agent_raw_logs(self, payload: object) -> dict[str, object]: ...


class AgentLogAnalysisMCPServer:
    """Thin MCP server shell for event-query tools."""

    def __init__(self, runtime: _RuntimeProtocol | None = None) -> None:
        self.runtime: _RuntimeProtocol | AgentLogAnalysisService = (
            runtime or AgentLogAnalysisService()
        )
        self._owns_runtime = runtime is None

    def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        params_repr = repr(params)
        if params_repr == "__unused__":
            return {}
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {
                "name": "agent-log-analysis-mcp",
                "version": "0.1.0",
            },
        }

    def handle_tools_list(self) -> dict[str, Any]:
        return {"tools": list_tools()}

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return MCPProtocol.error_response(None, INVALID_REQUEST_CODE, "Invalid Request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str) or not method:
            return MCPProtocol.error_response(
                request_id,
                INVALID_REQUEST_CODE,
                "Invalid Request",
            )
        return await MCPProtocol.resolve_request(self, request=request, logger=logger)

    async def start(self) -> None:
        if self._owns_runtime and isinstance(self.runtime, AgentLogAnalysisService):
            await self.runtime.start()

    async def close(self) -> None:
        if self._owns_runtime and isinstance(self.runtime, AgentLogAnalysisService):
            await self.runtime.stop()


async def main_async() -> None:
    server = AgentLogAnalysisMCPServer()
    framing: str | None = None
    try:
        await _run_server(server, framing)
    except BaseException:
        raise
    finally:
        await server.close()


async def _serve_messages(
    server: AgentLogAnalysisMCPServer,
    framing: str | None,
) -> None:
    current_framing = framing
    while True:
        request, current_framing = await read_message(
            sys.stdin.buffer,
            framing_hint=current_framing,
        )
        if request is None:
            return
        response = await server.handle_request(request)
        if response is not None:
            sys.stdout.buffer.write(encode_message(response, framing=current_framing or "newline"))
            sys.stdout.buffer.flush()


async def _run_server(
    server: AgentLogAnalysisMCPServer,
    framing: str | None,
) -> None:
    await server.start()
    await _serve_messages(server, framing)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
