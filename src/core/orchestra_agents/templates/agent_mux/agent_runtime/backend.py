"""Generic event-driven compatibility wrapper around agent-mux."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from core.llm_proxy.client_config import (
    DEFAULT_LLM_PROXY_API_KEY,
    ROUTE_POLICY_CODEX_ONLY,
    default_route_policy,
    resolve_llm_client_config,
    resolve_llm_proxy_api_key,
    resolve_llm_proxy_url,
)
from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    ClearContextRequest,
    EventDelivery,
    EventDeliveryResult,
    StopRequest,
)

from .dispatch import (
    AgentMuxDispatchSpec,
    build_agent_mux_command,
    parse_agent_mux_result,
    write_runtime_codex_config,
)
from .prompting import build_compact_wakeup_block, build_context_memory_block
from .state import AgentMuxRuntimeState, QueueEntry


logger = logging.getLogger(__name__)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_STANDARD_EVENT_KEYS = {
    "event_id",
    "thread_id",
    "root_thread_id",
    "parent_thread_id",
    "owner_agent_slug",
    "sequence_no",
    "event_kind",
    "notification_status",
    "from_agent_slug",
    "to_agent_slug",
    "message_text",
    "interrupts_runtime",
    "requires_response",
    "created_at",
}


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


def _normalize_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return int(text)


def _message_preview(text: str, *, limit: int = 200) -> str:
    preview = " ".join(str(text or "").split())
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(0, limit - 3)]}..."


def _sanitize_reply_text(text: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", str(text or ""))
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def _normalize_mcp_servers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        server = {str(key): item[key] for key in item.keys()}
        if str(server.get("name") or "").strip() and str(server.get("command") or "").strip():
            normalized.append(server)
    return normalized


def _extra_event_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, value in payload.items():
        normalized_key = str(key)
        if normalized_key in _STANDARD_EVENT_KEYS:
            continue
        extra[normalized_key] = value
    return extra


def _metadata_summary(payload: Mapping[str, Any]) -> Optional[str]:
    source_context = payload.get("source_context")
    if isinstance(source_context, Mapping) and source_context:
        parts: list[str] = []
        for key in ("channel", "sender_display", "chat_title", "received_at"):
            value = str(source_context.get(key) or "").strip()
            if value:
                parts.append(f"{key}={value}")
        if parts:
            return ", ".join(parts)
    extra = _extra_event_metadata(payload)
    if extra:
        return _message_preview(json.dumps(extra, ensure_ascii=False, sort_keys=True), limit=200)
    return None


def _extract_tool_calls(result: Mapping[str, Any]) -> list[str]:
    activity = result.get("activity")
    if not isinstance(activity, Mapping):
        return []
    tool_calls = activity.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [str(item).strip() for item in tool_calls if str(item).strip()]


def _dispatch_preview(result: Mapping[str, Any]) -> Optional[str]:
    response = _sanitize_reply_text(str(result.get("response") or ""))
    if response:
        return _message_preview(response, limit=400)
    summary = _sanitize_reply_text(str(result.get("handoff_summary") or ""))
    if summary:
        return _message_preview(summary, limit=400)
    tool_calls = _extract_tool_calls(result)
    if tool_calls:
        return f"tools: {', '.join(tool_calls[:6])}"
    return None


@dataclass(frozen=True)
class AgentMuxRuntimeSettings:
    http_endpoint: str
    agent_mux_binary: str
    state_root: str
    artifact_root: str
    role: str
    variant: Optional[str]
    max_attempts: int
    llm_proxy_url: str
    llm_proxy_api_key: str
    llm_route_policy: str
    default_model: str
    agent_timeout_seconds: int
    context_memory_entries: int
    require_tool_call_for_response: bool
    mcp_servers: tuple[dict[str, Any], ...]


class AgentMuxBackend(BaseAgentBackend):
    """Generic queue-first wrapper that feeds events into agent-mux."""

    def __init__(
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        config: Optional[dict[str, Any]] = None,
        system_prompt: str = "",
        http_endpoint: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_slug=agent_slug,
            backend_type=backend_type,
            working_dir=working_dir,
            config=config,
        )
        raw_config = dict(config or {})
        self.system_prompt = str(system_prompt or "").strip()
        llm_config = resolve_llm_client_config(
            {
                "route_policy": raw_config.get("llm_route_policy") or default_route_policy(),
                "model": raw_config.get("model") or os.getenv("LLM_CLIENT_MODEL"),
                "timeout_seconds": raw_config.get("timeout_seconds") or os.getenv("LLM_CLIENT_TIMEOUT_SECONDS"),
                "reasoning_effort": raw_config.get("reasoning_effort") or os.getenv("LLM_CLIENT_REASONING_EFFORT"),
                "reasoning_summary": raw_config.get("reasoning_summary") or os.getenv("LLM_CLIENT_REASONING_SUMMARY"),
                "text_verbosity": raw_config.get("text_verbosity") or os.getenv("LLM_CLIENT_TEXT_VERBOSITY"),
            }
        )
        state_root = (
            str(raw_config.get("state_root") or os.getenv("AGENT_MUX_STATE_ROOT") or os.path.join(working_dir, "runtime_state")).strip()
            or os.path.join(working_dir, "runtime_state")
        )
        self.settings = AgentMuxRuntimeSettings(
            http_endpoint=(str(http_endpoint or os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or "").rstrip("/")),
            agent_mux_binary=str(raw_config.get("agent_mux_binary") or os.getenv("AGENT_MUX_BINARY") or "agent-mux").strip() or "agent-mux",
            state_root=state_root,
            artifact_root=(
                str(raw_config.get("artifact_root") or os.path.join(state_root, "artifacts")).strip()
                or os.path.join(state_root, "artifacts")
            ),
            role=str(raw_config.get("role") or "worker").strip() or "worker",
            variant=(str(raw_config.get("variant") or "").strip() or None),
            max_attempts=max(1, _normalize_int(raw_config.get("max_attempts"), default=3)),
            llm_proxy_url=str(raw_config.get("llm_proxy_url") or resolve_llm_proxy_url()).rstrip("/"),
            llm_proxy_api_key=(
                str(raw_config.get("llm_proxy_api_key") or resolve_llm_proxy_api_key() or DEFAULT_LLM_PROXY_API_KEY).strip()
                or DEFAULT_LLM_PROXY_API_KEY
            ),
            llm_route_policy=str(llm_config.route_policy or ROUTE_POLICY_CODEX_ONLY).strip() or ROUTE_POLICY_CODEX_ONLY,
            default_model=str(llm_config.model or "gpt-5.4").strip() or "gpt-5.4",
            agent_timeout_seconds=max(30, _normalize_int(raw_config.get("timeout_seconds"), default=1800)),
            context_memory_entries=max(
                4,
                _normalize_int(raw_config.get("context_memory_entries") or os.getenv("AGENT_MUX_CONTEXT_MEMORY_ENTRIES"), default=16),
            ),
            require_tool_call_for_response=_normalize_bool(
                raw_config.get("require_tool_call_for_response"),
                default=False,
            ),
            mcp_servers=tuple(_normalize_mcp_servers(raw_config.get("mcp_servers"))),
        )
        self.runtime_state = AgentMuxRuntimeState(self.settings.state_root)
        persisted_context = self.runtime_state.context_snapshot()
        persisted_generation = persisted_context.get("context_generation")
        if persisted_generation is not None:
            self.context_generation = int(persisted_generation)
        self.current_context_id = self.runtime_state.ensure_context_id(
            fallback_context_id=self.current_context_id,
            generation=self.context_generation,
        )
        self._task_lock = asyncio.Lock()
        self._processor_task: Optional[asyncio.Task[None]] = None
        self._active_process: Optional[asyncio.subprocess.Process] = None
        self._active_dispatch_id: Optional[str] = None
        self._active_event_payload: Optional[dict[str, Any]] = None
        self.last_queued_event_id: Optional[str] = None
        self.last_queued_event_ids: list[str] = []
        self.last_duplicate_events = 0
        self.last_dispatch_id: Optional[str] = None
        self.last_dispatch_status: Optional[str] = None
        self.last_dispatch_reason: Optional[str] = None
        self.last_reply_preview: Optional[str] = None
        self.last_processed_event_id: Optional[str] = None
        self.last_processed_event_kind: Optional[str] = None
        self.last_tool_calls: list[str] = []

    async def on_start(self) -> None:
        self.runtime_state.ensure_layout()
        self.current_context_id = self.runtime_state.ensure_context_id(
            fallback_context_id=self.current_context_id,
            generation=self.context_generation,
        )
        if self.runtime_state.queue_size() > 0:
            await self._schedule_processor()

    async def on_shutdown(self) -> None:
        async with self._task_lock:
            process = self._active_process
            processor_task = self._processor_task
        if process is not None and process.returncode is None:
            process.terminate()
        if processor_task is not None:
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
        self._clear_active_context()

    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        self.remember_delivery(delivery)
        queue_result = self.runtime_state.queue_delivery(delivery)
        self.last_queued_event_ids = list(queue_result["queued_event_ids"])
        self.last_queued_event_id = self.last_queued_event_ids[-1] if self.last_queued_event_ids else None
        self.last_duplicate_events = int(queue_result["duplicate_events"])

        if any(event.interrupts_runtime for event in delivery.events):
            await self._interrupt_active_dispatch(reason=f"incoming {delivery.events[-1].event_kind}")

        if queue_result["queued_events"] > 0:
            await self._schedule_processor()

        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=delivery.delivery_id,
            duplicate=bool(queue_result["queued_events"] == 0 and queue_result["duplicate_events"] > 0),
            details={
                "backend_type": self.backend_type,
                "wrapper_mode": "agent_mux_codex_generic",
                "queue_size": queue_result["queue_size"],
                "queued_events": queue_result["queued_events"],
                "duplicate_events": queue_result["duplicate_events"],
                "queued_event_ids": queue_result["queued_event_ids"],
                "last_event_id": self.last_queued_event_id,
            },
        )

    async def stop(self, request: StopRequest) -> dict[str, Any]:
        payload = await super().stop(request)
        cleared_queue = 0
        if request.thread_id or request.parent_thread_id:
            cleared_queue = self.runtime_state.clear_entries_matching(
                thread_id=request.thread_id,
                parent_thread_id=request.parent_thread_id,
            )
            if self._active_event_matches_filters(
                thread_id=request.thread_id,
                parent_thread_id=request.parent_thread_id,
            ):
                await self._interrupt_active_dispatch(reason=request.reason)
        else:
            await self._interrupt_active_dispatch(reason=request.reason)
        payload.update(
            {
                "wrapper_mode": "agent_mux_codex_generic",
                "cleared_queue_events": cleared_queue,
            }
        )
        return payload

    async def last_status(self) -> dict[str, Any]:
        payload = await super().last_status()
        payload.update(
            {
                "http_endpoint": self.settings.http_endpoint,
                "wrapper_mode": "agent_mux_codex_generic",
                "agent_mux_binary": self.settings.agent_mux_binary,
                "llm_proxy_url": self.settings.llm_proxy_url,
                "llm_route_policy": self.settings.llm_route_policy,
                "default_model": self.settings.default_model,
                "configured_mcp_servers": [item["name"] for item in self.settings.mcp_servers],
                "require_tool_call_for_response": self.settings.require_tool_call_for_response,
                "last_queued_event_id": self.last_queued_event_id,
                "last_queued_event_ids": list(self.last_queued_event_ids),
                "last_duplicate_events": self.last_duplicate_events,
                "last_dispatch_id": self.last_dispatch_id,
                "last_dispatch_status": self.last_dispatch_status,
                "last_dispatch_reason": self.last_dispatch_reason,
                "last_reply_preview": self.last_reply_preview,
                "last_processed_event_id": self.last_processed_event_id,
                "last_processed_event_kind": self.last_processed_event_kind,
                "last_tool_calls": list(self.last_tool_calls),
                "runtime_context": self.runtime_state.context_snapshot(),
                "runtime_state": self.runtime_state.status_snapshot(),
                "active_dispatch_id": self._active_dispatch_id,
                "active_process_running": bool(self._active_process and self._active_process.returncode is None),
            }
        )
        return payload

    async def clear_context(self, request: ClearContextRequest) -> dict[str, Any]:
        previous_context_id = self.current_context_id
        payload = await super().clear_context(request)
        self.runtime_state.save_context_id(
            context_id=self.current_context_id,
            previous_context_id=previous_context_id,
            generation=self.context_generation,
        )
        self._clear_active_context()
        async with self._task_lock:
            process = self._active_process
            processor_task = self._processor_task
        if process is not None and process.returncode is None:
            process.terminate()
        if processor_task is not None:
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
        self._processor_task = None
        self._active_process = None
        self._active_dispatch_id = None
        self._active_event_payload = None
        cleared_pending_entries = self.runtime_state.clear_all_pending_entries()
        self.runtime_state.reset_runtime_metadata()
        self.last_queued_event_id = None
        self.last_queued_event_ids = []
        self.last_duplicate_events = 0
        self.last_dispatch_id = None
        self.last_dispatch_status = None
        self.last_dispatch_reason = None
        self.last_reply_preview = None
        self.last_processed_event_id = None
        self.last_processed_event_kind = None
        self.last_tool_calls = []
        payload.update(
            {
                "wrapper_mode": "agent_mux_codex_generic",
                "cleared_pending_entries": cleared_pending_entries,
                "runtime_context": self.runtime_state.context_snapshot(),
                "runtime_state": self.runtime_state.status_snapshot(),
            }
        )
        return payload

    async def _schedule_processor(self) -> None:
        async with self._task_lock:
            if self._processor_task is not None and not self._processor_task.done():
                return
            self._processor_task = asyncio.create_task(
                self._process_queue(),
                name=f"{self.agent_slug}-event-processor",
            )

    async def _process_queue(self) -> None:
        try:
            while True:
                entry = self.runtime_state.claim_next_entry()
                if entry is None:
                    break
                attempts = int(entry.payload.get("attempt_count") or 0)
                try:
                    await self._process_queue_entry(entry)
                    self.runtime_state.complete_entry(entry)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_dispatch_status = "failed"
                    self.last_dispatch_reason = str(exc)
                    if attempts + 1 >= self.settings.max_attempts:
                        logger.warning("discarding queue entry %s after error: %s", entry.queue_id, exc)
                        self.runtime_state.discard_entry(entry, error_text=str(exc))
                    else:
                        logger.warning("requeueing queue entry %s after error: %s", entry.queue_id, exc)
                        self.runtime_state.requeue_entry(entry, error_text=str(exc))
                        await asyncio.sleep(min(5, attempts + 1))
        finally:
            async with self._task_lock:
                current = self._processor_task
                if current is asyncio.current_task():
                    self._processor_task = None

    async def _process_queue_entry(self, entry: QueueEntry) -> None:
        payload = entry.payload
        event_payload = payload.get("payload")
        if not isinstance(event_payload, dict):
            raise RuntimeError("queue entry is missing payload")
        event = EventDelivery.from_dict({"delivery_id": payload.get("delivery_id"), "events": [event_payload]}).events[0]
        self.last_processed_event_id = event.event_id
        self.last_processed_event_kind = event.event_kind
        self._remember_incoming_context(event)
        if not self._is_actionable_event(event):
            return

        dispatch_id = uuid.uuid4().hex
        artifact_dir = self.runtime_state.artifact_dir_for_dispatch(dispatch_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_state.remember_active_dispatch(
            dispatch_id=dispatch_id,
            event_id=event.event_id,
            event_kind=event.event_kind,
            artifact_dir=str(artifact_dir),
            queue_id=entry.queue_id,
        )
        self._write_active_context(self._active_context_payload(event))
        async with self._task_lock:
            self._active_dispatch_id = dispatch_id
            self._active_event_payload = dict(event.raw_payload)
        try:
            result = await self._run_agent_mux(
                event=event,
                dispatch_id=dispatch_id,
                artifact_dir=artifact_dir,
            )
            status = str(result.get("status") or "").strip().lower() or "failed"
            tool_calls = _extract_tool_calls(result)
            preview = _dispatch_preview(result)
            self.last_dispatch_id = dispatch_id
            self.last_dispatch_status = status
            self.last_dispatch_reason = str(result.get("reason") or "").strip() or None
            self.last_tool_calls = tool_calls
            self.last_reply_preview = preview
            self.runtime_state.remember_dispatch_result(
                context_id=self.current_context_id,
                dispatch_id=dispatch_id,
                session_id=((result.get("metadata") or {}).get("session_id") if isinstance(result.get("metadata"), dict) else None),
                event_id=event.event_id,
                event_kind=event.event_kind,
            )
            if status != "completed":
                reason = str(result.get("reason") or result.get("error") or "agent-mux execution failed").strip()
                raise RuntimeError(reason or "agent-mux execution failed")
            if self.settings.require_tool_call_for_response and event.requires_response and not tool_calls:
                raise RuntimeError("dispatch completed without any tool call for a response-required event")
            self._remember_agent_output(event=event, result=result)
        finally:
            self.runtime_state.clear_active_dispatch(dispatch_id)
            self._clear_active_context()
            async with self._task_lock:
                self._active_dispatch_id = None
                self._active_event_payload = None
                self._active_process = None

    def _is_actionable_event(self, event: Any) -> bool:
        return bool(event.requires_response) or bool(event.interrupts_runtime)

    async def _run_agent_mux(
        self,
        *,
        event: Any,
        dispatch_id: str,
        artifact_dir: Path,
    ) -> dict[str, Any]:
        codex_home = self.runtime_state.codex_home_dir()
        active_context_path = str(self.runtime_state.active_context_path)
        pythonpath = str(os.getenv("PYTHONPATH") or f"/workspace/src:{self.working_dir}")
        write_runtime_codex_config(
            codex_home=codex_home,
            llm_proxy_url=self.settings.llm_proxy_url,
            route_policy=self.settings.llm_route_policy,
            model=self.settings.default_model,
            agent_slug=self.agent_slug,
            active_context_path=active_context_path,
            pythonpath=pythonpath,
            agent_working_dir=self.working_dir,
            mcp_servers=self.settings.mcp_servers,
        )
        prompt = self._build_dispatch_prompt(event=event)
        spec = AgentMuxDispatchSpec(
            dispatch_id=dispatch_id,
            prompt=prompt,
            cwd=self.working_dir,
            artifact_dir=str(artifact_dir),
            system_prompt=self.system_prompt,
            role=self.settings.role,
            variant=self.settings.variant,
            model=self.settings.default_model,
            timeout_sec=self.settings.agent_timeout_seconds,
            engine_opts={"close_stdin_after_start": True},
        )
        command = build_agent_mux_command(self.settings.agent_mux_binary)
        env = os.environ.copy()
        env["HOME"] = str(codex_home)
        env["CODEX_HOME"] = str(codex_home / ".codex")
        env["LLM_PROXY_API_KEY"] = self.settings.llm_proxy_api_key
        env["ORCHESTRA_AGENT_SLUG"] = self.agent_slug
        env["ORCHESTRA_CONTEXT_ID"] = self.current_context_id
        env["AGENT_MUX_CONTEXT_ID"] = self.current_context_id
        env["AGENT_MUX_EVENT_ID"] = str(event.event_id or dispatch_id)
        env["AGENT_MUX_EVENT_KIND"] = str(event.event_kind or "event")
        env["AGENT_MUX_DISPATCH_ID"] = dispatch_id
        env["AGENT_MUX_ACTIVE_CONTEXT_PATH"] = active_context_path
        env["ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH"] = active_context_path
        stdin_payload = json.dumps(spec.to_stdin_payload(), ensure_ascii=False).encode("utf-8")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env=env,
        )
        async with self._task_lock:
            self._active_process = process
        stdout_data, stderr_data = await process.communicate(stdin_payload)
        if process.returncode != 0:
            error_text = stderr_data.decode("utf-8", errors="replace").strip() or stdout_data.decode("utf-8", errors="replace").strip()
            raise RuntimeError(error_text or f"agent-mux exited with code {process.returncode}")
        return parse_agent_mux_result(stdout_data.decode("utf-8", errors="replace"))

    def _build_dispatch_prompt(self, *, event: Any) -> str:
        wakeup = build_compact_wakeup_block(
            event=event,
            folded_event_count=0,
        )
        context_memory = build_context_memory_block(
            context_id=self.current_context_id,
            entries=self.runtime_state.context_snapshot().get("recent_entries") or [],
        )
        active_event_json = json.dumps(self._active_context_payload(event), ensure_ascii=False, indent=2)
        return "\n\n".join(
            [
                "You are handling one incoming agent event.",
                "Use configured tools or MCP servers for any external side effects.",
                "Plain assistant text is not automatically delivered to upstream systems.",
                "If the event requires a response, emit the necessary tool actions before you finish.",
                wakeup,
                context_memory,
                f"Active event payload:\n{active_event_json}",
            ]
        ).strip()

    def _remember_incoming_context(self, event: Any) -> None:
        self.runtime_state.append_context_entry(
            context_id=self.current_context_id,
            role="source",
            event_id=event.event_id,
            event_kind=event.event_kind,
            source_agent_slug=event.from_agent_slug,
            text=event.message_text,
            metadata_summary=_metadata_summary(event.raw_payload),
            max_entries=self.settings.context_memory_entries,
        )

    def _remember_agent_output(self, *, event: Any, result: Mapping[str, Any]) -> None:
        preview = _dispatch_preview(result) or "dispatch completed"
        tool_calls = _extract_tool_calls(result)
        metadata_summary = None
        if tool_calls:
            metadata_summary = f"tool_calls={', '.join(tool_calls[:6])}"
        self.runtime_state.append_context_entry(
            context_id=self.current_context_id,
            role="agent",
            event_id=event.event_id,
            event_kind=event.event_kind,
            source_agent_slug=self.agent_slug,
            text=preview,
            metadata_summary=metadata_summary,
            max_entries=self.settings.context_memory_entries,
        )

    def _active_context_payload(self, event: Any) -> dict[str, Any]:
        payload = {
            "context_id": self.current_context_id,
            "event_id": event.event_id,
            "event_kind": event.event_kind,
            "from_agent_slug": event.from_agent_slug,
            "to_agent_slug": event.to_agent_slug,
            "created_at": event.created_at,
            "message_text": event.message_text,
            "requires_response": bool(event.requires_response),
            "interrupts_runtime": bool(event.interrupts_runtime),
        }
        for optional_key in ("thread_id", "root_thread_id", "parent_thread_id", "owner_agent_slug", "notification_status"):
            value = getattr(event, optional_key, None)
            if value is not None:
                payload[optional_key] = value
        metadata = _extra_event_metadata(event.raw_payload)
        if metadata:
            payload["metadata"] = metadata
        return payload

    def _active_event_matches_filters(self, *, thread_id: Optional[str], parent_thread_id: Optional[str]) -> bool:
        payload = self._active_event_payload or {}
        normalized_thread_id = str(thread_id or "").strip()
        normalized_parent_thread_id = str(parent_thread_id or "").strip()
        if normalized_thread_id and str(payload.get("thread_id") or "").strip() == normalized_thread_id:
            return True
        if normalized_parent_thread_id and str(payload.get("parent_thread_id") or "").strip() == normalized_parent_thread_id:
            return True
        return False

    async def _interrupt_active_dispatch(self, *, reason: str) -> None:
        async with self._task_lock:
            process = self._active_process
            dispatch_id = self._active_dispatch_id
        if process is None or process.returncode is not None:
            return
        logger.info("interrupting active dispatch %s: %s", dispatch_id or "unknown", reason)
        process.terminate()

    def _write_active_context(self, payload: dict[str, Any]) -> None:
        path = self.runtime_state.active_context_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)

    def _clear_active_context(self) -> None:
        try:
            self.runtime_state.active_context_path.unlink()
        except FileNotFoundError:
            return
