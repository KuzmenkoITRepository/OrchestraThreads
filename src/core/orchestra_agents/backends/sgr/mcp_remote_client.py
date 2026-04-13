"""HTTP-based remote MCP client with bearer auth."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from core.orchestra_agents.backends.sgr import _mcp_http_helpers as _http
from core.orchestra_agents.backends.sgr.mcp_protocol import MCPServerProtocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteMCPConfig:
    """Configuration for a remote HTTP MCP endpoint."""

    url: str
    bearer_token: str
    tools: list[str] | None = None  # Optional tool whitelist
    timeout_seconds: int = 30


class RemoteHTTPMCPServer(MCPServerProtocol):
    """MCP server that proxies tool calls to a remote HTTP endpoint."""

    def __init__(self, config: RemoteMCPConfig) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    async def handle_tools_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a remote tool call via HTTP POST /mcp."""
        session = await self._get_session()
        payload = _http.build_payload(name, arguments)
        headers = _http.build_headers(self._config.bearer_token)

        try:
            return await _http.execute_call(session, self._config.url, payload, headers)
        except aiohttp.ClientError as exc:
            logger.exception("Remote MCP call failed for %s: %s", name, exc)
            return {"ok": False, "error": f"Connection error: {exc}"}
        except json.JSONDecodeError as exc:
            logger.exception("Remote MCP invalid JSON response for %s", name)
            return {"ok": False, "error": f"Invalid JSON: {exc}"}
        except Exception as exc:
            logger.exception("Remote MCP unexpected error for %s", name)
            return {"ok": False, "error": f"Unexpected error: {exc}"}

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session


def create_remote_server(
    url: str,
    bearer_token: str,
    tools: list[str] | None = None,
    timeout_seconds: int = 30,
) -> RemoteHTTPMCPServer:
    """Factory function to create a remote HTTP MCP server."""
    config = RemoteMCPConfig(
        url=url,
        bearer_token=bearer_token,
        tools=tools,
        timeout_seconds=timeout_seconds,
    )
    return RemoteHTTPMCPServer(config)
