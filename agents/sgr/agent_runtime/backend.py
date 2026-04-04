"""Backend adapter for the proactive SGR Minimax agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from core.llm_proxy.client_config import (
    LLM_PROXY_TRACE_AGENT_HEADER,
    LLM_PROXY_TRACE_CONTEXT_HEADER,
    ROUTE_POLICY_MINIMAX_ONLY,
    build_llm_proxy_openai_base_url,
    llm_proxy_enabled,
    resolve_llm_client_config,
    resolve_llm_proxy_api_key,
)
from core.llm_proxy.protocol import (
    flatten_content,
    openai_chat_payload_to_codex_response,
    tool_calls_to_openai,
)
from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    ClearContextRequest,
    EventDelivery,
    EventDeliveryResult,
)
from core.orchestra_thread.active_context import (
    clear_active_context,
    write_active_context,
)
from core.orchestra_thread.client import OrchestraThreadsClient
from core.orchestra_thread.mcp_server import OrchestraThreadsMCPServer

logger = logging.getLogger(__name__)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _message_preview(text: str, *, limit: int = 160) -> str:
    preview = " ".join(str(text or "").split())
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(0, limit - 3)]}..."


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return float(text)


def _normalize_int(value: Any, *, default: int, minimum: int = 1) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return max(minimum, int(text))


def _strip_think_blocks(text: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", str(text or ""))
    return cleaned.strip()


@dataclass(frozen=True)
class SGRRuntimeSettings:
    threads_url: str | None
    http_endpoint: str
    heartbeat_interval_seconds: float
    guide_view: str
    react_to_inactive: bool
    max_reasoning_steps: int
    max_direct_text_retries: int


@dataclass
class ToolExecutionOutcome:
    tool_name: str
    result_text: str
    emitted_message: bool = False
    published_status: str | None = None
    message_preview: str | None = None
    route: str | None = None


@dataclass
class AgentTurnOutcome:
    llm_turns: int = 0
    tool_calls: int = 0
    messages_sent: int = 0
    statuses_published: int = 0
    used_tools: list[str] = field(default_factory=list)
    direct_text_ignored: bool = False
    ignored_text_preview: str | None = None
    last_reply_preview: str | None = None
    last_status_preview: str | None = None
    last_published_status: str | None = None

    @property
    def action_emitted(self) -> bool:
        return self.messages_sent > 0 or self.statuses_published > 0


class SGRMinimaxBackend(BaseAgentBackend):
    """Tool-driven backend that answers only through OrchestraThreads MCP tools."""

    def __init__(
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        config: dict[str, Any] | None = None,
        system_prompt: str = "",
        http_endpoint: str | None = None,
    ) -> None:
        super().__init__(
            agent_slug=agent_slug,
            backend_type=backend_type,
            working_dir=working_dir,
            config=config,
        )
        self.system_prompt = str(system_prompt or "").strip()
        raw_config = dict(config or {})
        llm_raw_config = {
            "route_policy": raw_config.get("route_policy") or ROUTE_POLICY_MINIMAX_ONLY,
            "model": raw_config.get("model"),
            "timeout_seconds": raw_config.get("timeout_seconds"),
            "temperature": raw_config.get("temperature"),
            "max_tokens": raw_config.get("max_tokens"),
            "text_verbosity": raw_config.get("text_verbosity"),
            "reasoning_effort": raw_config.get("reasoning_effort"),
            "reasoning_summary": raw_config.get("reasoning_summary"),
        }
        self.llm_config = resolve_llm_client_config(llm_raw_config)
        threads_url_raw = raw_config.get("threads_url")
        if threads_url_raw is None:
            threads_url_raw = os.getenv("ORCHESTRA_THREADS_URL")
        self.settings = SGRRuntimeSettings(
            threads_url=_normalize_optional_str(
                threads_url_raw.rstrip("/") if isinstance(threads_url_raw, str) else threads_url_raw
            ),
            http_endpoint=(
                str(http_endpoint or os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or "").rstrip("/")
            ),
            heartbeat_interval_seconds=max(
                2.0,
                _normalize_float(
                    os.getenv("SGR_HEARTBEAT_INTERVAL_SECONDS")
                    or raw_config.get("heartbeat_interval_seconds"),
                    default=10.0,
                ),
            ),
            guide_view=str(raw_config.get("guide_view") or "compact").strip().lower() or "compact",
            react_to_inactive=_normalize_bool(raw_config.get("react_to_inactive"), default=True),
            max_reasoning_steps=_normalize_int(
                os.getenv("SGR_MAX_REASONING_STEPS") or raw_config.get("max_reasoning_steps"),
                default=8,
                minimum=1,
            ),
            max_direct_text_retries=_normalize_int(
                os.getenv("SGR_MAX_DIRECT_TEXT_RETRIES")
                or raw_config.get("max_direct_text_retries"),
                default=2,
                minimum=0,
            ),
        )
        self.thread_client: OrchestraThreadsClient | None = None
        self.mcp_server: OrchestraThreadsMCPServer | None = None
        self._openai_tools = self._build_openai_tools()
        self._http_session: aiohttp.ClientSession | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._registered_in_threads = False
        self._guide_loaded = False
        self._guide_text: str = ""
        self._turn_lock = asyncio.Lock()
        self.last_thread_id: str | None = None
        self.last_peer_agent_slug: str | None = None
        self.last_reply_preview: str | None = None
        self.last_status_preview: str | None = None
        self.last_published_status: str | None = None
        self.last_ignored_output_preview: str | None = None
        self.last_llm_model: str | None = None
        self.last_delivery_duplicate = False
        self.last_action_emitted = False
        self.last_tool_actions: list[str] = []
        self.handled_event_ids: set[str] = set()
        self.handled_event_order: list[str] = []

    async def on_start(self) -> None:
        if not llm_proxy_enabled():
            raise RuntimeError("LLM_PROXY_ENABLED=false, but the sgr example requires llm_proxy")
        clear_active_context()

    async def on_shutdown(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        clear_active_context()
        if self.mcp_server is not None:
            await self.mcp_server.close()
            self.mcp_server = None
            self.thread_client = None

    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        async with self._turn_lock:
            self.remember_delivery(delivery)
            actionable_events = [
                event for event in delivery.events if self._is_actionable_event(event)
            ]
            if not actionable_events:
                self.last_delivery_duplicate = False
                self.last_action_emitted = False
                self.last_tool_actions = []
                self.last_ignored_output_preview = None
                return EventDeliveryResult(
                    accepted=True,
                    accepted_events=len(delivery.events),
                    delivery_id=delivery.delivery_id,
                    details={
                        "backend_type": self.backend_type,
                        "skipped": len(delivery.events),
                        "reason": "no_actionable_events",
                    },
                )

            event = actionable_events[-1]
            event_id = self._event_identity(event)
            if event_id in self.handled_event_ids:
                self.last_delivery_duplicate = True
                self.last_action_emitted = False
                return EventDeliveryResult(
                    accepted=True,
                    accepted_events=len(delivery.events),
                    delivery_id=delivery.delivery_id,
                    duplicate=True,
                    details={
                        "backend_type": self.backend_type,
                        "thread_id": event.thread_id,
                        "event_id": event_id,
                    },
                )

            thread_summary: dict[str, Any] = {}
            if event.thread_id:
                await self._ensure_thread_registration()
                await self._refresh_guide()
                compact_payload = await self._thread_client().get_thread_compact(
                    thread_id=event.thread_id
                )
                thread_summary = compact_payload.get("thread") or {}
                peer_agent_slug = self._peer_agent_slug(thread_summary=thread_summary, event=event)
            else:
                peer_agent_slug = _normalize_optional_str(event.from_agent_slug) or "unknown"
            outcome = await self._run_turn(
                delivery=delivery,
                primary_event=event,
                thread_summary=thread_summary,
                peer_agent_slug=peer_agent_slug,
            )
            if event.thread_id and event.requires_response and not outcome.action_emitted:
                raise RuntimeError(
                    "SGR turn completed without emitting any orchestra-thread MCP action for a response-required event"
                )

            self.last_thread_id = event.thread_id
            self.last_peer_agent_slug = peer_agent_slug
            self.last_reply_preview = outcome.last_reply_preview
            self.last_status_preview = outcome.last_status_preview
            self.last_published_status = outcome.last_published_status
            self.last_ignored_output_preview = outcome.ignored_text_preview
            self.last_action_emitted = outcome.action_emitted
            self.last_tool_actions = list(outcome.used_tools[-16:])
            self.last_delivery_duplicate = False
            self._remember_handled_event(event_id)
            details: dict[str, Any] = {
                "backend_type": self.backend_type,
                "thread_id": event.thread_id,
                "event_id": event_id,
                "peer_agent_slug": peer_agent_slug,
                "llm_model": self.last_llm_model,
                "action_emitted": outcome.action_emitted,
                "llm_turns": outcome.llm_turns,
                "tool_calls": outcome.tool_calls,
                "messages_sent": outcome.messages_sent,
                "statuses_published": outcome.statuses_published,
                "used_tools": list(outcome.used_tools[-16:]),
                "direct_text_ignored": outcome.direct_text_ignored,
            }
            if outcome.last_published_status:
                details["published_status"] = outcome.last_published_status
            if not outcome.action_emitted:
                details["reason"] = "no_tool_action_emitted"
            return EventDeliveryResult(
                accepted=True,
                accepted_events=len(delivery.events),
                delivery_id=delivery.delivery_id,
                details=details,
            )

    async def last_status(self) -> dict[str, Any]:
        payload = await super().last_status()
        payload.update(
            {
                "threads_url": self.settings.threads_url,
                "http_endpoint": self.settings.http_endpoint,
                "route_policy": self.llm_config.route_policy,
                "llm_model": self.last_llm_model or self.llm_config.model,
                "last_thread_id": self.last_thread_id,
                "last_peer_agent_slug": self.last_peer_agent_slug,
                "last_reply_preview": self.last_reply_preview,
                "last_status_preview": self.last_status_preview,
                "last_published_status": self.last_published_status,
                "last_ignored_output_preview": self.last_ignored_output_preview,
                "last_delivery_duplicate": self.last_delivery_duplicate,
                "last_action_emitted": self.last_action_emitted,
                "last_tool_actions": list(self.last_tool_actions),
                "registered_in_threads": self._registered_in_threads,
            }
        )
        return payload

    async def clear_context(self, request: ClearContextRequest) -> dict[str, Any]:
        payload = await super().clear_context(request)
        self.last_thread_id = None
        self.last_peer_agent_slug = None
        self.last_reply_preview = None
        self.last_status_preview = None
        self.last_published_status = None
        self.last_ignored_output_preview = None
        self.last_llm_model = None
        self.last_delivery_duplicate = False
        self.last_action_emitted = False
        self.last_tool_actions = []
        self.handled_event_ids.clear()
        self.handled_event_order.clear()
        clear_active_context()
        return payload

    async def _register_with_thread_service(self) -> None:
        await self._thread_client().register_agent(
            agent_slug=self.agent_slug,
            display_name=self.agent_slug,
            base_url=self.settings.http_endpoint,
            metadata={
                "kind": "sgr-minimax-tool-agent",
                "backend_type": self.backend_type,
                "route_policy": self.llm_config.route_policy,
                "model": self.llm_config.model,
                "tool_surface": "orchestra-threads-mcp",
            },
        )

    async def _refresh_guide(self) -> None:
        if self._guide_loaded:
            return
        if not self.settings.threads_url:
            return
        try:
            payload = await self._thread_client().get_instruction(
                view=self.settings.guide_view, section="mcp"
            )
        except Exception as exc:
            logger.warning("failed to fetch OrchestraThreads guide: %s", exc)
            return
        instruction = payload.get("instruction") if isinstance(payload, dict) else None
        if isinstance(instruction, dict):
            self._guide_text = str(instruction.get("text") or "").strip()
        self._guide_loaded = True

    def _thread_registration_enabled(self) -> bool:
        return bool(self.settings.threads_url and self.settings.http_endpoint)

    async def _ensure_thread_registration(self) -> None:
        if self._registered_in_threads:
            return
        if not self._thread_registration_enabled():
            return
        await self._register_with_thread_service()
        self._registered_in_threads = True
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name=f"{self.agent_slug}-heartbeat"
            )

    def _thread_client(self) -> OrchestraThreadsClient:
        if self.thread_client is None:
            if not self.settings.threads_url:
                raise RuntimeError("ORCHESTRA_THREADS_URL is required for thread operations")
            self.thread_client = OrchestraThreadsClient(
                base_url=self.settings.threads_url,
                timeout_seconds=max(
                    1.0,
                    float(
                        self.llm_config.timeout_seconds
                        or os.getenv("ORCHESTRA_THREADS_HTTP_TIMEOUT_SECONDS", "10")
                    ),
                ),
            )
        return self.thread_client

    def _mcp_server(self) -> OrchestraThreadsMCPServer:
        if self.mcp_server is None:
            self.mcp_server = OrchestraThreadsMCPServer(
                agent_slug=self.agent_slug, client=self._thread_client()
            )
        return self.mcp_server

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.settings.heartbeat_interval_seconds)
                if not self._registered_in_threads:
                    continue
                await self._thread_client().heartbeat(agent_slug=self.agent_slug)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("heartbeat failed for %s: %s", self.agent_slug, exc)
                try:
                    if self._thread_registration_enabled():
                        await self._register_with_thread_service()
                        self._registered_in_threads = True
                except Exception as register_exc:
                    logger.warning("re-register failed for %s: %s", self.agent_slug, register_exc)

    def _build_openai_tools(self) -> list[dict[str, Any]]:
        tool_entries = [
            {
                "name": "thread_send",
                "description": "Send a thread message using compact auto-routing based on the active invocation context.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "target_agent_slug": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": ["auto", "root", "child", "exact"],
                        },
                        "thread_id": {"type": "string"},
                        "client_request_id": {"type": "string"},
                    },
                    "required": ["message"],
                },
            },
            {
                "name": "thread_status",
                "description": "Publish thread status updates without repeating thread_id when an active context exists.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["in_progress", "review", "done", "closed"],
                        },
                        "message": {"type": "string"},
                        "thread_id": {"type": "string"},
                        "target_agent_slug": {"type": "string"},
                        "client_request_id": {"type": "string"},
                    },
                    "required": ["status", "message"],
                },
            },
            {
                "name": "thread_current",
                "description": "Return compact current-thread state for the active invocation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"thread_id": {"type": "string"}},
                },
            },
            {
                "name": "thread_expand",
                "description": "Expand thread details on demand. Use sparingly when compact state is insufficient.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string"},
                        "view": {
                            "type": "string",
                            "enum": ["latest", "tail", "related", "full"],
                        },
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "thread_guide",
                "description": "Fetch the canonical OrchestraThreads workflow and routing/status rules from the service.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "view": {"type": "string", "enum": ["compact", "full"]},
                        "section": {
                            "type": "string",
                            "enum": [
                                "overview",
                                "workflow",
                                "routing",
                                "statuses",
                                "delivery",
                                "mcp",
                                "mcp_tools",
                            ],
                        },
                    },
                },
            },
        ]
        converted: list[dict[str, Any]] = []
        for entry in tool_entries:
            if not isinstance(entry, dict):
                continue
            name = _normalize_optional_str(entry.get("name"))
            if not name:
                continue
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(entry.get("description") or "").strip(),
                        "parameters": entry.get("inputSchema")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        return converted

    def _is_actionable_event(self, event: Any) -> bool:
        if event.event_kind == "message":
            return bool(event.requires_response)
        if event.event_kind == "inactive":
            return self.settings.react_to_inactive
        return False

    def _event_identity(self, event: Any) -> str:
        return (
            _normalize_optional_str(event.event_id)
            or ":".join(
                part
                for part in (
                    _normalize_optional_str(event.thread_id),
                    str(event.sequence_no) if event.sequence_no is not None else None,
                    _normalize_optional_str(event.event_kind),
                )
                if part
            )
            or f"delivery-{uuid.uuid4().hex}"
        )

    def _remember_handled_event(self, event_id: str) -> None:
        if event_id in self.handled_event_ids:
            return
        self.handled_event_ids.add(event_id)
        self.handled_event_order.append(event_id)
        if len(self.handled_event_order) <= 512:
            return
        stale = self.handled_event_order.pop(0)
        self.handled_event_ids.discard(stale)

    def _peer_agent_slug(self, *, thread_summary: dict[str, Any], event: Any) -> str:
        participant_a = _normalize_optional_str(thread_summary.get("participant_a_agent_slug"))
        participant_b = _normalize_optional_str(thread_summary.get("participant_b_agent_slug"))
        if participant_a == self.agent_slug and participant_b:
            return participant_b
        if participant_b == self.agent_slug and participant_a:
            return participant_a
        fallback = _normalize_optional_str(event.from_agent_slug)
        if fallback and fallback != self.agent_slug:
            return fallback
        raise RuntimeError(f"Unable to resolve peer agent for thread {event.thread_id}")

    async def _session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            timeout_seconds = max(1.0, float(self.llm_config.timeout_seconds or 120))
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout_seconds)
            )
        return self._http_session

    async def _run_turn(
        self,
        *,
        delivery: EventDelivery,
        primary_event: Any,
        thread_summary: dict[str, Any],
        peer_agent_slug: str,
    ) -> AgentTurnOutcome:
        messages = self._build_messages(
            delivery=delivery,
            primary_event=primary_event,
            thread_summary=thread_summary,
            peer_agent_slug=peer_agent_slug,
        )
        outcome = AgentTurnOutcome()
        direct_text_retries = 0
        with self._active_context_scope(
            event=primary_event,
            thread_summary=thread_summary,
            peer_agent_slug=peer_agent_slug,
        ):
            for _ in range(self.settings.max_reasoning_steps):
                response_payload = await self._post_llm_request(
                    {
                        "model": self.llm_config.model,
                        "messages": messages,
                        "tools": self._openai_tools,
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                        "stream": False,
                        "agent_slug": self.agent_slug,
                        "thread_id": primary_event.thread_id,
                        "root_thread_id": primary_event.root_thread_id,
                        "parent_thread_id": primary_event.parent_thread_id,
                        "request_scope": "orchestra_thread_tool_loop",
                        **self._optional_llm_args(),
                    }
                )
                outcome.llm_turns += 1
                assistant_message, assistant_text, tool_calls = self._extract_completion(
                    response_payload
                )
                messages.append(assistant_message)
                if tool_calls:
                    direct_text_retries = 0
                    for tool_call in tool_calls:
                        outcome.tool_calls += 1
                        function = tool_call.get("function") if isinstance(tool_call, dict) else {}
                        tool_name = _normalize_optional_str(
                            function.get("name") if isinstance(function, dict) else None
                        )
                        outcome.used_tools.append(tool_name or "unknown_tool")
                        execution = await self._execute_tool_call(tool_call)
                        if execution.emitted_message:
                            outcome.messages_sent += 1
                            outcome.last_reply_preview = execution.message_preview
                        if execution.published_status:
                            outcome.statuses_published += 1
                            outcome.last_published_status = execution.published_status
                            outcome.last_status_preview = execution.message_preview
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": str(tool_call.get("id") or "").strip(),
                                "content": execution.result_text or "(empty tool result)",
                            }
                        )
                    continue

                if assistant_text:
                    outcome.direct_text_ignored = True
                    outcome.ignored_text_preview = _message_preview(assistant_text)

                if outcome.action_emitted:
                    return outcome

                if direct_text_retries >= self.settings.max_direct_text_retries:
                    return outcome

                direct_text_retries += 1
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Direct assistant text is never delivered to the peer. "
                            "Emit the next action only through OrchestraThreads MCP tools. "
                            "Use thread_send for any reply and thread_status for progress or lifecycle updates."
                        ),
                    }
                )
        return outcome

    def _optional_llm_args(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.llm_config.temperature is not None:
            payload["temperature"] = self.llm_config.temperature
        if self.llm_config.max_tokens is not None:
            payload["max_tokens"] = self.llm_config.max_tokens
        return payload

    def _build_messages(
        self,
        *,
        delivery: EventDelivery,
        primary_event: Any,
        thread_summary: dict[str, Any],
        peer_agent_slug: str,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "system", "content": self._tool_runtime_rules()})
        operational_notes = self._operational_notes(
            thread_summary=thread_summary, peer_agent_slug=peer_agent_slug
        )
        if operational_notes:
            messages.append({"role": "system", "content": operational_notes})
        messages.append(
            {
                "role": "user",
                "content": self._build_wake_up_block(
                    delivery=delivery,
                    primary_event=primary_event,
                    thread_summary=thread_summary,
                    peer_agent_slug=peer_agent_slug,
                ),
            }
        )
        return messages

    def _tool_runtime_rules(self) -> str:
        rules = [
            "You are running inside an OrchestraThreads agent runtime.",
            "All outward communication must happen through OrchestraThreads MCP tools.",
            "Use thread_send for any peer-facing message.",
            "Use thread_status for in_progress, review, done, or closed updates.",
            "If the active thread state is unclear, call thread_current first.",
            "Use thread_expand only when compact state is insufficient.",
            "Use thread_guide when you need to refresh service workflow or routing rules.",
            "Plain assistant text is not delivered to the peer and is treated as discarded scratch output.",
            "For a response-required message event, do not finish the turn without emitting at least one thread_send or thread_status action.",
            "On inactive wake-ups, act proactively: send a follow-up, publish status, request review, or close when work is actually finished.",
            "Keep tool messages concise, concrete, and operational.",
            "Do not mention manifests, callback URLs, thread ids, llm_proxy, Docker, or runtime internals in peer-facing content.",
        ]
        return "\n".join(f"- {item}" for item in rules)

    def _operational_notes(self, *, thread_summary: dict[str, Any], peer_agent_slug: str) -> str:
        notes: list[str] = []
        if self._guide_text:
            notes.append(self._guide_text)
        compact_lines = [
            "Compact thread state:",
            f"- thread_id: {thread_summary.get('thread_id') or '-'}",
            f"- root_thread_id: {thread_summary.get('root_thread_id') or '-'}",
            f"- parent_thread_id: {thread_summary.get('parent_thread_id') or '-'}",
            f"- scope: {thread_summary.get('scope') or '-'}",
            f"- status: {thread_summary.get('status') or '-'}",
            f"- owner_agent_slug: {thread_summary.get('owner_agent_slug') or '-'}",
            f"- peer_agent_slug: {peer_agent_slug or '-'}",
            f"- last_event_kind: {thread_summary.get('last_event_kind') or '-'}",
            f"- last_event_from_agent_slug: {thread_summary.get('last_event_from_agent_slug') or '-'}",
            f"- last_event_to_agent_slug: {thread_summary.get('last_event_to_agent_slug') or '-'}",
            f"- last_event_message_preview: {thread_summary.get('last_event_message_preview') or '-'}",
        ]
        notes.append("\n".join(compact_lines))
        return "\n\n".join(part for part in notes if part).strip()

    def _build_wake_up_block(
        self,
        *,
        delivery: EventDelivery,
        primary_event: Any,
        thread_summary: dict[str, Any],
        peer_agent_slug: str,
    ) -> str:
        scope = str(thread_summary.get("scope") or "unknown").strip() or "unknown"
        participant_a = (
            _normalize_optional_str(thread_summary.get("participant_a_agent_slug")) or "unknown"
        )
        participant_b = (
            _normalize_optional_str(thread_summary.get("participant_b_agent_slug")) or "unknown"
        )
        status = str(thread_summary.get("status") or "open").strip() or "open"
        owner_agent_slug = (
            _normalize_optional_str(thread_summary.get("owner_agent_slug")) or "unknown"
        )
        folded = max(0, len(delivery.events) - 1)
        event_label = primary_event.event_kind
        if primary_event.event_kind == "notification" and primary_event.notification_status:
            event_label = f"notification:{primary_event.notification_status}"
        ask_line = str(primary_event.message_text or "").strip()
        if primary_event.event_kind == "inactive":
            ask_line = "Inactivity wake-up. Decide whether to follow up, publish status, request review, or close if the work is done."
        lines = [
            "=== THREAD UPDATE ===",
            f"thread: {primary_event.thread_id} {scope} {participant_a}<->{participant_b}",
            f"state: {status}, owner={owner_agent_slug}, peer={peer_agent_slug}",
            f"new: {event_label} from {primary_event.from_agent_slug or 'unknown'}",
        ]
        if ask_line:
            lines.append(f"ask: {ask_line}")
        if thread_summary.get("last_event_message_preview"):
            lines.append(f"last: {thread_summary.get('last_event_message_preview')}")
        if folded > 0:
            lines.append(f"note: {folded} older event(s) were folded into this wake-up.")
        return "\n".join(lines)

    def _active_context_payload(
        self,
        *,
        event: Any,
        thread_summary: dict[str, Any],
        peer_agent_slug: str,
    ) -> dict[str, Any]:
        return {
            "agent_slug": self.agent_slug,
            "thread_id": event.thread_id,
            "root_thread_id": event.root_thread_id or thread_summary.get("root_thread_id"),
            "parent_thread_id": event.parent_thread_id or thread_summary.get("parent_thread_id"),
            "source_agent_slug": peer_agent_slug,
            "target_agent_slug": self.agent_slug,
            "owner_agent_slug": thread_summary.get("owner_agent_slug"),
            "current_mode": "reply",
        }

    def _active_context_scope(
        self, *, event: Any, thread_summary: dict[str, Any], peer_agent_slug: str
    ):
        backend = self

        class _Scope:
            def __enter__(self_nonlocal):
                write_active_context(
                    backend._active_context_payload(
                        event=event,
                        thread_summary=thread_summary,
                        peer_agent_slug=peer_agent_slug,
                    )
                )
                return self_nonlocal

            def __exit__(self_nonlocal, exc_type, exc, tb):
                del exc_type, exc, tb
                clear_active_context()
                return False

        return _Scope()

    async def _post_llm_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = await self._session()
        headers = {
            "Content-Type": "application/json",
            LLM_PROXY_TRACE_AGENT_HEADER: self.agent_slug,
            LLM_PROXY_TRACE_CONTEXT_HEADER: str(payload.get("thread_id") or self.agent_slug),
        }
        api_key = resolve_llm_proxy_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = (
            build_llm_proxy_openai_base_url(self.llm_config.route_policy).rstrip("/")
            + "/chat/completions"
        )
        async with session.post(url, json=payload, headers=headers) as response:
            raw = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"llm_proxy chat request failed: HTTP {response.status}: {raw}")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"llm_proxy returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("llm_proxy returned a non-object payload")
        return parsed

    def _extract_completion(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        response = openai_chat_payload_to_codex_response(payload)
        self.last_llm_model = response.model or self.llm_config.model
        assistant_text = _strip_think_blocks(response.text)
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_text or None,
        }
        tool_calls = tool_calls_to_openai(response.tool_calls)
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        return assistant_message, assistant_text, tool_calls or []

    async def _execute_tool_call(self, tool_call: dict[str, Any]) -> ToolExecutionOutcome:
        function = tool_call.get("function") if isinstance(tool_call, dict) else {}
        if not isinstance(function, dict):
            function = {}
        tool_name = _normalize_optional_str(function.get("name")) or "unknown_tool"
        raw_arguments = function.get("arguments")
        try:
            if isinstance(raw_arguments, dict):
                arguments = dict(raw_arguments)
            elif isinstance(raw_arguments, str) and raw_arguments.strip():
                arguments = json.loads(raw_arguments)
            else:
                arguments = {}
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        result = await self._mcp_server().handle_tools_call(name=tool_name, arguments=arguments)
        result_text = flatten_content(result.get("content"))
        if not result_text:
            result_text = json.dumps(result, ensure_ascii=False)
        structured = (
            result.get("structuredContent")
            if isinstance(result.get("structuredContent"), dict)
            else {}
        )
        failed = bool(result.get("isError")) or not bool(structured.get("ok", True))
        outcome = ToolExecutionOutcome(
            tool_name=tool_name,
            result_text=result_text,
        )
        if failed:
            return outcome
        if tool_name == "thread_send":
            outcome.emitted_message = True
            outcome.message_preview = _message_preview(str(arguments.get("message") or ""))
            outcome.route = _normalize_optional_str(structured.get("route"))
            return outcome
        if tool_name == "thread_status":
            outcome.published_status = _normalize_optional_str(
                structured.get("published_status")
            ) or _normalize_optional_str(arguments.get("status"))
            outcome.message_preview = _message_preview(str(arguments.get("message") or ""))
        return outcome
