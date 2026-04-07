"""Backend adapter for the proactive SGR Minimax agent."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from agents.sgr.agent_runtime import backend_components as _components
from core.orchestra_agents import runtime as _rt
from core.orchestra_agents.templates.opencode.agent_runtime import (
    backend_registration as _registration,
)

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.mcp_protocol import MCPServerProtocol
    from core.orchestra_thread.client import OrchestraThreadsClient


class SGRMinimaxBackend(_rt.BaseAgentBackend):
    """Event-driven backend that answers through injected MCP tools."""

    def __init__(  # noqa: WPS211 — extends parent's 4-arg constructor
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        config: dict[str, object] | None = None,
        system_prompt: str = "",
    ) -> None:
        super().__init__(
            agent_slug=agent_slug,
            backend_type=backend_type,
            working_dir=working_dir,
            config=config,
        )
        from agents.sgr.agent_runtime import config_builder as _cfg

        raw = dict(config or {})
        self.system_prompt = str(system_prompt or "").strip()
        self.llm_config = _cfg.build_llm_config(raw)
        self.settings = _cfg.build_settings(raw)
        self._llm = _components.build_llm_client(
            agent_slug=agent_slug,
            route_policy=self.llm_config.route_policy,
            timeout_seconds=self.llm_config.timeout_seconds,
        )
        self._mcp_servers: dict[str, MCPServerProtocol] = {}
        self._openai_tools = _components.build_openai_tools()
        self._status = _components.build_status()
        persist_dir = str(Path(working_dir) / "runtime_state" / "chat_history")
        self._chat_history = _components.build_chat_history(persist_dir)
        self._turn_lock = asyncio.Lock()
        self.handled_event_ids: set[str] = set()
        self.handled_event_order: list[str] = []
        self.http_endpoint: str | None = None
        self._threads_client: OrchestraThreadsClient | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def on_start(self) -> None:
        """Register with orchestra-threads and start heartbeat."""
        await _registration.register_with_threads(self)

    async def on_shutdown(self) -> None:
        """Shut down heartbeat, LLM client, and MCP servers."""
        await _registration.stop_registration(self)
        close_tasks = [srv.close() for srv in self._mcp_servers.values()]
        await asyncio.gather(*close_tasks)
        await self._llm.close()

    async def handle_events(
        self,
        delivery: _rt.EventDelivery,
        *,
        is_interrupt: bool = False,
    ) -> _rt.EventDeliveryResult:
        """Route event delivery through the event processing pipeline."""
        async with self._turn_lock:
            from agents.sgr.agent_runtime import event_routing as _routing

            return await _routing.handle_events(self, delivery)

    async def last_status(self) -> dict[str, object]:
        """Return current backend status."""
        payload = await super().last_status()
        payload["route_policy"] = self.llm_config.route_policy
        payload["llm_model"] = self._status.llm_model or self.llm_config.model
        payload["mcp_tools"] = sorted(self._mcp_servers.keys())
        payload.update(self._status.to_dict())
        return payload

    async def clear_context(self, request: _rt.ClearContextRequest) -> dict[str, object]:
        """Reset internal state."""
        payload = await super().clear_context(request)
        self._status.reset()
        self._chat_history.clear()
        self.handled_event_ids.clear()
        self.handled_event_order.clear()
        return payload

    async def reset_session(self, routing_key: str) -> dict[str, object]:
        """Reset context for a specific session."""
        self._chat_history.clear_session(routing_key)
        payload = await super().reset_session(routing_key)
        return payload


def configure_mcp_tools(
    backend: SGRMinimaxBackend,
    mcp_servers: dict[str, MCPServerProtocol],
    tool_schemas: list[dict[str, object]] | None = None,
) -> None:
    """Inject MCP servers and optional tool schemas into the backend."""
    from agents.sgr.agent_runtime import tool_definitions as _tool_defs

    backend._mcp_servers = dict(mcp_servers)
    backend._openai_tools = _tool_defs.build_sgr_openai_tools(
        backend._mcp_servers,
        tool_schemas=list(tool_schemas or []),
    )
