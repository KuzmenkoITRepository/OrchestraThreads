"""Backend adapter for the proactive SGR Minimax agent."""

from __future__ import annotations

import asyncio

from agents.sgr.agent_runtime import event_routing as _routing
from core.orchestra_agents import runtime as _rt
from core.orchestra_thread import active_context as _active_ctx


class SGRMinimaxBackend(_rt.BaseAgentBackend):
    """Tool-driven backend that answers only through OrchestraThreads MCP tools."""

    def __init__(
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
        from agents.sgr.agent_runtime import context_memory as _memory
        from agents.sgr.agent_runtime import llm_client as _llm_mod
        from agents.sgr.agent_runtime import status_tracking as _status_mod
        from agents.sgr.agent_runtime import thread_ops as _thread_mod
        from agents.sgr.agent_runtime import tool_definitions as _tool_defs

        self.system_prompt = str(system_prompt or "").strip()
        raw = dict(config or {})
        self.llm_config = _cfg.build_llm_config(raw)
        self.settings = _cfg.build_settings(raw)
        self._llm = _llm_mod.SGRLLMClient(
            agent_slug=agent_slug,
            route_policy=self.llm_config.route_policy,
            timeout_seconds=self.llm_config.timeout_seconds,
        )
        self._thread_ops = _thread_mod.SGRThreadOps(
            agent_slug=agent_slug,
            settings=self.settings,
            llm_timeout_seconds=self.llm_config.timeout_seconds,
            metadata=_thread_mod._AgentMetadata(
                backend_type=backend_type,
                route_policy=self.llm_config.route_policy,
                model=self.llm_config.model or "gpt-5.4",
            ),
        )
        self._openai_tools = _tool_defs.build_sgr_openai_tools()
        self._status = _status_mod.SGRBackendStatus()
        self._context_memory = _memory.ContextMemory()
        self._turn_lock = asyncio.Lock()
        self.handled_event_ids: set[str] = set()
        self.handled_event_order: list[str] = []

    async def on_start(self) -> None:
        if not _llm_proxy_enabled():
            raise RuntimeError("LLM_PROXY_ENABLED=false, but the sgr example requires llm_proxy")
        _active_ctx.clear_active_context()

    async def on_shutdown(self) -> None:
        await self._thread_ops.shutdown()
        await self._llm.close()
        self._context_memory.clear()
        _active_ctx.clear_active_context()

    async def handle_events(
        self,
        delivery: _rt.EventDelivery,
        *,
        is_interrupt: bool = False,
    ) -> _rt.EventDeliveryResult:
        async with self._turn_lock:
            if is_interrupt:
                _active_ctx.clear_active_context()
            return await _routing.handle_events(self, delivery)

    async def last_status(self) -> dict[str, object]:
        payload = await super().last_status()
        payload["threads_url"] = self.settings.threads_url
        payload["http_endpoint"] = self.settings.http_endpoint
        payload["route_policy"] = self.llm_config.route_policy
        payload["llm_model"] = self._status.llm_model or self.llm_config.model
        payload["registered_in_threads"] = self._thread_ops.registered
        payload.update(self._status.to_dict())
        return payload

    async def clear_context(self, request: _rt.ClearContextRequest) -> dict[str, object]:
        payload = await super().clear_context(request)
        self._status.reset()
        self._context_memory.clear()
        self.handled_event_ids.clear()
        self.handled_event_order.clear()
        _active_ctx.clear_active_context()
        return payload


def _llm_proxy_enabled() -> bool:
    import os

    value = os.getenv("LLM_PROXY_ENABLED")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off", ""}
