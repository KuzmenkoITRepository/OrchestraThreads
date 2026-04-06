from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from core.llm_proxy._accounts_core import (
    build_account_status_rows,
    load_runtime_state_or_default,
    mutate_runtime_state,
    prune_runtime_state,
    resolve_profile_ids,
    utc_now_iso,
)
from core.llm_proxy._langfuse_runtime import (
    GENERATION_NAME_CODEX,
    GENERATION_NAME_FALLBACK,
    LangfuseTelemetry,
    model_parameters,
    normalize_usage,
    summarize_codex_response,
    summarize_openai_response,
    summarize_request_input,
    truncate_text,
)
from core.llm_proxy.client_config import (
    ROUTE_POLICY_CODEX_ONLY,
    ROUTE_POLICY_MANAGED_AUTO,
    ROUTE_POLICY_MINIMAX_ONLY,
    normalize_route_policy,
)
from core.llm_proxy.protocol import (
    AllCodexAccountsUnavailable,
    CodexModelResponse,
    CodexUpstreamError,
    build_chat_completion_response,
    build_instructions,
    codex_input_items_to_openai_messages,
    codex_tools_to_openai_tools,
    openai_chat_payload_to_codex_response,
    openai_messages_to_codex_input,
    openai_tools_to_codex,
)
from core.llm_proxy.transports import (
    CodexDirectTransport,
    OpenAICompatibleTransport,
    looks_like_minimax_model,
)


class UnifiedLLMRouter:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        auth_profiles_path: Path,
        profile_id: str | None,
        request_timeout_seconds: int,
        text_verbosity: str,
        reasoning_effort: str | None,
        reasoning_summary: str,
        temperature: float | None,
        profile_ids: list[str] | tuple[str, ...] | None = None,
        rotation_state_path: Path | None = None,
        account_failure_cooldown_seconds: int = 120,
        fallback_base_url: str | None = None,
        fallback_api_key: str | None = None,
        fallback_model: str | None = None,
        fallback_timeout_seconds: int = 120,
        telemetry: LangfuseTelemetry | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.auth_profiles_path = auth_profiles_path
        self.profile_id = profile_id
        self.profile_ids = tuple(
            str(item).strip() for item in (profile_ids or []) if str(item).strip()
        )
        self.rotation_state_path = rotation_state_path or (
            auth_profiles_path.parent / "proxy-state.json"
        )
        self.account_failure_cooldown_seconds = max(1, account_failure_cooldown_seconds)
        self.transport = CodexDirectTransport(
            model=model,
            base_url=base_url,
            auth_profiles_path=auth_profiles_path,
            request_timeout_seconds=request_timeout_seconds,
            text_verbosity=text_verbosity,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary,
            temperature=temperature,
        )
        self.fallback_transport = OpenAICompatibleTransport(
            base_url=fallback_base_url,
            api_key=fallback_api_key,
            model=fallback_model,
            request_timeout_seconds=fallback_timeout_seconds,
        )
        self.telemetry = telemetry or LangfuseTelemetry()
        self._runtime_state_lock = threading.Lock()
        with self._runtime_state_lock:
            mutate_runtime_state(
                self.rotation_state_path,
                lambda payload: self._sync_runtime_state_payload(payload),
            )

    def _request_trace_metadata(
        self,
        *,
        route_policy: str,
        effective_model: str,
        agent_slug: str | None,
        context_id: str | None,
        trace_metadata_overrides: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = {
            "agent_slug": str(agent_slug or "").strip() or None,
            "context_id": str(context_id or "").strip() or None,
            "thread_id": None,
            "root_thread_id": None,
            "parent_thread_id": None,
            "origin_channel": None,
            "request_scope": None,
            "request_kind": None,
            "request_path": None,
            "route_policy": route_policy,
            "effective_model": effective_model,
            "stream": None,
        }
        for key in (
            "thread_id",
            "root_thread_id",
            "parent_thread_id",
            "origin_channel",
            "request_scope",
            "request_kind",
            "request_path",
            "stream",
        ):
            if trace_metadata_overrides and trace_metadata_overrides.get(key) is not None:
                payload[key] = trace_metadata_overrides.get(key)
        return {metadata_key: value for metadata_key, value in payload.items() if value is not None}

    def _trace_tags(self, *, route_policy: str, agent_slug: str | None) -> list[str]:
        tags = ["service:llm_proxy", f"route:{route_policy}"]
        normalized_agent = str(agent_slug or "").strip()
        if normalized_agent:
            tags.append(f"agent:{normalized_agent}")
        return tags

    def _resolved_profile_ids(self) -> list[str]:
        return resolve_profile_ids(
            self.auth_profiles_path,
            configured_profile_ids=self.profile_ids or None,
            primary_profile_id=self.profile_id,
        )

    def _sync_runtime_state_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_ids = self._resolved_profile_ids()
        payload = prune_runtime_state(payload, profile_ids)
        payload["updated_at"] = utc_now_iso()
        payload["fallback"] = {
            **(payload.get("fallback") or {}),
            "enabled": self.fallback_transport.enabled,
            "model": self.fallback_transport.model or None,
        }
        profiles = payload.setdefault("profiles", {})
        for profile_id in profile_ids:
            profiles.setdefault(
                profile_id,
                {
                    "status": "ready",
                    "disabled_until": None,
                    "last_error": None,
                    "last_error_at": None,
                    "last_success_at": None,
                    "success_count": 0,
                    "failure_count": 0,
                },
            )
        return payload

    def _candidate_profile_ids(self) -> list[str]:
        now_ts = time.time()
        with self._runtime_state_lock:
            result: dict[str, list[str]] = {"ordered": []}

            def _update(payload: dict[str, Any]) -> dict[str, Any]:
                payload = self._sync_runtime_state_payload(payload)
                profile_ids = self._resolved_profile_ids()
                available: list[str] = []
                profiles = payload.setdefault("profiles", {})
                for profile_id in profile_ids:
                    state = profiles.setdefault(profile_id, {})
                    disabled_until = state.get("disabled_until")
                    disabled_until_ts = (
                        float(disabled_until) if isinstance(disabled_until, int | float) else None
                    )
                    if disabled_until_ts and disabled_until_ts > now_ts:
                        continue
                    available.append(profile_id)
                if not available:
                    result["ordered"] = []
                    return payload
                rotation_index = int(payload.get("rotation_index") or 0)
                start_index = rotation_index % len(available)
                result["ordered"] = available[start_index:] + available[:start_index]
                payload["rotation_index"] = rotation_index + 1
                return payload

            mutate_runtime_state(self.rotation_state_path, _update)
            return result["ordered"]

    def _record_profile_success(self, profile_id: str) -> None:
        with self._runtime_state_lock:

            def _update(payload: dict[str, Any]) -> dict[str, Any]:
                payload = self._sync_runtime_state_payload(payload)
                state = payload["profiles"].setdefault(profile_id, {})
                state["status"] = "ready"
                state["disabled_until"] = None
                state["last_error"] = None
                state["last_error_at"] = None
                state["last_success_at"] = utc_now_iso()
                state["success_count"] = int(state.get("success_count") or 0) + 1
                return payload

            mutate_runtime_state(self.rotation_state_path, _update)

    def _record_profile_failure(self, profile_id: str, exc: CodexUpstreamError) -> None:
        with self._runtime_state_lock:

            def _update(payload: dict[str, Any]) -> dict[str, Any]:
                payload = self._sync_runtime_state_payload(payload)
                state = payload["profiles"].setdefault(profile_id, {})
                state["failure_count"] = int(state.get("failure_count") or 0) + 1
                state["last_error"] = str(exc)
                state["last_error_at"] = utc_now_iso()
                if exc.should_try_next_profile:
                    state["status"] = "cooldown"
                    state["disabled_until"] = time.time() + self.account_failure_cooldown_seconds
                else:
                    state["status"] = "error"
                return payload

            mutate_runtime_state(self.rotation_state_path, _update)

    def _record_fallback_result(self, *, error: str | None = None) -> None:
        with self._runtime_state_lock:

            def _update(payload: dict[str, Any]) -> dict[str, Any]:
                payload = self._sync_runtime_state_payload(payload)
                fallback = payload.setdefault("fallback", {})
                if error:
                    fallback["last_error"] = error
                    fallback["last_error_at"] = utc_now_iso()
                else:
                    fallback["last_used_at"] = utc_now_iso()
                    fallback["last_error"] = None
                    fallback["last_error_at"] = None
                return payload

            mutate_runtime_state(self.rotation_state_path, _update)

    def describe_accounts(self) -> dict[str, Any]:
        return {
            "profiles": build_account_status_rows(
                self.auth_profiles_path,
                self.rotation_state_path,
                configured_profile_ids=self.profile_ids or None,
                primary_profile_id=self.profile_id,
            ),
            "fallback": load_runtime_state_or_default(self.rotation_state_path).get("fallback", {}),
            "primary_profile_id": self.profile_id,
            "configured_profile_ids": list(self.profile_ids),
        }

    def _fallback_payload_from_codex_request(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if instructions.strip():
            messages.append({"role": "system", "content": instructions})
        messages.extend(codex_input_items_to_openai_messages(input_items))
        fallback_model = str(self.fallback_transport.model or "").strip()
        payload: dict[str, Any] = {
            "model": fallback_model or model or self.model,
            "messages": messages,
            "stream": False,
        }
        openai_tools = codex_tools_to_openai_tools(tools)
        if openai_tools:
            payload["tools"] = openai_tools
            payload["tool_choice"] = "auto"
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    def _select_model_for_route(self, requested_model: str | None, *, route_policy: str) -> str:
        normalized_route_policy = normalize_route_policy(route_policy)
        requested = str(requested_model or "").strip()
        fallback_model = str(self.fallback_transport.model or "").strip()
        if normalized_route_policy == ROUTE_POLICY_MINIMAX_ONLY:
            return requested or fallback_model or self.model
        if not requested:
            return self.model
        if looks_like_minimax_model(requested):
            return self.model
        if fallback_model and requested == fallback_model:
            return self.model
        return requested

    def complete(self, **kwargs: Any) -> CodexModelResponse:
        instructions = str(kwargs.get("instructions") or "")
        input_items: list[dict[str, Any]] = list(kwargs.get("input_items") or [])
        tools: list[dict[str, Any]] | None = kwargs.get("tools")
        session_id = kwargs.get("session_id")
        cancel_event = kwargs.get("cancel_event")
        model = kwargs.get("model")
        text_verbosity = kwargs.get("text_verbosity")
        reasoning_effort = kwargs.get("reasoning_effort")
        reasoning_summary = kwargs.get("reasoning_summary")
        temperature = kwargs.get("temperature")
        route_policy = str(kwargs.get("route_policy") or ROUTE_POLICY_MANAGED_AUTO)
        agent_slug = kwargs.get("agent_slug")
        context_id = kwargs.get("context_id")
        trace_metadata_overrides: dict[str, Any] | None = kwargs.get("trace_metadata_overrides")

        normalized_route_policy = normalize_route_policy(route_policy)
        effective_model = self._select_model_for_route(model, route_policy=normalized_route_policy)
        attempts: list[dict[str, Any]] = []
        request_metadata = self._request_trace_metadata(
            route_policy=normalized_route_policy,
            effective_model=effective_model,
            agent_slug=agent_slug,
            context_id=context_id,
            trace_metadata_overrides=trace_metadata_overrides,
        )
        request_summary = summarize_request_input(
            instructions=instructions,
            input_items=input_items,
            tools=tools,
            model=model or effective_model,
            route_policy=normalized_route_policy,
            request_metadata=request_metadata,
        )
        with self.telemetry.start_request(
            request_kind=str(request_metadata.get("request_kind") or "responses"),
            agent_slug=agent_slug,
            context_id=context_id,
            metadata=request_metadata,
            input_payload=request_summary,
            tags=self._trace_tags(route_policy=normalized_route_policy, agent_slug=agent_slug),
        ) as request_trace:
            try:
                if normalized_route_policy == ROUTE_POLICY_MINIMAX_ONLY:
                    return self._complete_minimax_only(
                        effective_model=effective_model,
                        request_trace=request_trace,
                        request_summary=request_summary,
                        instructions=instructions,
                        input_items=input_items,
                        tools=tools,
                        temperature=temperature,
                    )
                response = self._complete_codex_profiles(
                    effective_model=effective_model,
                    request_trace=request_trace,
                    request_summary=request_summary,
                    instructions=instructions,
                    input_items=input_items,
                    tools=tools,
                    session_id=session_id,
                    cancel_event=cancel_event,
                    text_verbosity=text_verbosity,
                    reasoning_effort=reasoning_effort,
                    reasoning_summary=reasoning_summary,
                    temperature=temperature,
                    route_policy=normalized_route_policy,
                    attempts=attempts,
                )
                if response is not None:
                    return response
                if (
                    normalized_route_policy != ROUTE_POLICY_CODEX_ONLY
                    and self.fallback_transport.enabled
                ):
                    return self._complete_fallback_after_codex(
                        effective_model=effective_model,
                        request_trace=request_trace,
                        request_summary=request_summary,
                        instructions=instructions,
                        input_items=input_items,
                        tools=tools,
                        temperature=temperature,
                        route_policy=normalized_route_policy,
                        attempts=attempts,
                    )
                if attempts:
                    raise AllCodexAccountsUnavailable(attempts)
                raise RuntimeError("No Codex OAuth profiles are available")
            except Exception as exc:
                request_trace.mark_error(
                    error=exc,
                    output={
                        "error": truncate_text(exc, limit=300),
                        "attempts": attempts,
                        "route_policy": normalized_route_policy,
                    },
                    metadata={"outcome": "error"},
                )
                raise

    def _complete_minimax_only(
        self,
        *,
        effective_model: str,
        request_trace: Any,
        request_summary: dict[str, Any],
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
    ) -> CodexModelResponse:
        if not self.fallback_transport.supports(model_override=effective_model):
            raise RuntimeError(
                "llm_proxy minimax_only route requested but fallback is not configured"
            )
        fallback_request_payload = self._fallback_payload_from_codex_request(
            instructions=instructions,
            input_items=input_items,
            tools=tools,
            model=effective_model,
            temperature=temperature,
        )
        fallback_payload = self._run_fallback_generation(
            request_trace=request_trace,
            request_summary=request_summary,
            effective_model=effective_model,
            route_policy=ROUTE_POLICY_MINIMAX_ONLY,
            fallback_request_payload=fallback_request_payload,
            model_override=effective_model,
            codex_attempts=0,
        )
        self._record_fallback_result()
        response = openai_chat_payload_to_codex_response(fallback_payload)
        request_trace.mark_success(
            output=summarize_codex_response(response),
            metadata={
                "selected_transport": "fallback",
                "fallback_used": "true",
            },
        )
        return response

    def _complete_codex_profiles(
        self,
        *,
        effective_model: str,
        request_trace: Any,
        request_summary: dict[str, Any],
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        session_id: str | None,
        cancel_event: threading.Event | None,
        text_verbosity: str | None,
        reasoning_effort: str | None,
        reasoning_summary: str | None,
        temperature: float | None,
        route_policy: str,
        attempts: list[dict[str, Any]],
    ) -> CodexModelResponse | None:
        for profile_id in self._candidate_profile_ids():
            response = self._run_codex_generation(
                request_trace=request_trace,
                request_summary=request_summary,
                effective_model=effective_model,
                route_policy=route_policy,
                profile_id=profile_id,
                instructions=instructions,
                input_items=input_items,
                tools=tools,
                session_id=session_id,
                cancel_event=cancel_event,
                text_verbosity=text_verbosity,
                reasoning_effort=reasoning_effort,
                reasoning_summary=reasoning_summary,
                temperature=temperature,
                attempts=attempts,
            )
            if response is not None:
                return response
        return None

    def _run_codex_generation(
        self,
        *,
        request_trace: Any,
        request_summary: dict[str, Any],
        effective_model: str,
        route_policy: str,
        profile_id: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        session_id: str | None,
        cancel_event: threading.Event | None,
        text_verbosity: str | None,
        reasoning_effort: str | None,
        reasoning_summary: str | None,
        temperature: float | None,
        attempts: list[dict[str, Any]],
    ) -> CodexModelResponse | None:
        with request_trace.generation(
            name=GENERATION_NAME_CODEX,
            model=effective_model,
            input_payload=request_summary,
            metadata={
                "transport": "codex",
                "profile_id": profile_id,
                "route_policy": route_policy,
            },
            model_parameters_payload=model_parameters(
                temperature=temperature,
                text_verbosity=text_verbosity,
                reasoning_effort=reasoning_effort,
                reasoning_summary=reasoning_summary,
            ),
        ) as generation:
            started_at = time.perf_counter()
            try:
                response = self.transport.complete(
                    profile_id=profile_id,
                    instructions=instructions,
                    input_items=input_items,
                    tools=tools,
                    session_id=session_id,
                    cancel_event=cancel_event,
                    model=effective_model,
                    text_verbosity=text_verbosity,
                    reasoning_effort=reasoning_effort,
                    reasoning_summary=reasoning_summary,
                    temperature=temperature,
                )
            except CodexUpstreamError as exc:
                self._record_codex_error(
                    generation=generation,
                    profile_id=profile_id,
                    exc=exc,
                    attempts=attempts,
                    started_at=started_at,
                )
                if exc.should_try_next_profile:
                    return None
                raise
            self._record_codex_success(
                generation=generation,
                request_trace=request_trace,
                response=response,
                profile_id=profile_id,
                started_at=started_at,
            )
            return response

    def _record_codex_error(
        self,
        *,
        generation: Any,
        profile_id: str,
        exc: CodexUpstreamError,
        attempts: list[dict[str, Any]],
        started_at: float,
    ) -> None:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        self._record_profile_failure(profile_id, exc)
        attempts.append(
            {
                "profile_id": profile_id,
                "error": str(exc),
                "status_code": exc.status_code,
            }
        )
        generation.update(
            output={"error": truncate_text(exc, limit=300)},
            metadata={
                "transport": "codex",
                "profile_id": profile_id,
                "latency_ms": latency_ms,
                "outcome": "error",
                "status_code": exc.status_code,
            },
            level="ERROR",
            status_message=truncate_text(exc, limit=300),
        )

    def _record_codex_success(
        self,
        *,
        generation: Any,
        request_trace: Any,
        response: CodexModelResponse,
        profile_id: str,
        started_at: float,
    ) -> None:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        self._record_profile_success(profile_id)
        generation.update(
            output=summarize_codex_response(response),
            usage_details=normalize_usage(response.usage),
            metadata={
                "transport": "codex",
                "profile_id": profile_id,
                "latency_ms": latency_ms,
                "outcome": "success",
            },
        )
        request_trace.mark_success(
            output=summarize_codex_response(response),
            metadata={
                "selected_transport": "codex",
                "selected_profile_id": profile_id,
                "fallback_used": "false",
            },
        )

    def _complete_fallback_after_codex(
        self,
        *,
        effective_model: str,
        request_trace: Any,
        request_summary: dict[str, Any],
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        route_policy: str,
        attempts: list[dict[str, Any]],
    ) -> CodexModelResponse:
        fallback_request_payload = self._fallback_payload_from_codex_request(
            instructions=instructions,
            input_items=input_items,
            tools=tools,
            model=effective_model,
            temperature=temperature,
        )
        fallback_payload = self._run_fallback_generation(
            request_trace=request_trace,
            request_summary=request_summary,
            effective_model=effective_model,
            route_policy=route_policy,
            fallback_request_payload=fallback_request_payload,
            model_override=None,
            codex_attempts=len(attempts),
        )
        self._record_fallback_result()
        response = openai_chat_payload_to_codex_response(fallback_payload)
        request_trace.mark_success(
            output=summarize_codex_response(response),
            metadata={
                "selected_transport": "fallback",
                "fallback_used": "true",
                "codex_attempts": str(len(attempts)),
            },
        )
        return response

    def _run_fallback_generation(
        self,
        *,
        request_trace: Any,
        request_summary: dict[str, Any],
        effective_model: str,
        route_policy: str,
        fallback_request_payload: dict[str, Any],
        model_override: str | None,
        codex_attempts: int,
    ) -> dict[str, Any]:
        generation_metadata: dict[str, Any] = {
            "transport": "fallback",
            "route_policy": route_policy,
        }
        if codex_attempts:
            generation_metadata["codex_attempts"] = codex_attempts
        with request_trace.generation(
            name=GENERATION_NAME_FALLBACK,
            model=effective_model,
            input_payload=request_summary,
            metadata=generation_metadata,
            model_parameters_payload=model_parameters(
                temperature=fallback_request_payload.get("temperature")
            ),
        ) as generation:
            started_at = time.perf_counter()
            try:
                fallback_payload = self.fallback_transport.complete_chat(
                    fallback_request_payload,
                    model_override=model_override,
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                generation.update(
                    output={"error": truncate_text(exc, limit=300)},
                    metadata={
                        "transport": "fallback",
                        "latency_ms": latency_ms,
                        "outcome": "error",
                    },
                    level="ERROR",
                    status_message=truncate_text(exc, limit=300),
                )
                self._record_fallback_result(error=str(exc))
                raise
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            success_metadata = {
                "transport": "fallback",
                "latency_ms": latency_ms,
                "outcome": "success",
            }
            if codex_attempts:
                success_metadata["codex_attempts"] = codex_attempts
            generation.update(
                output=summarize_openai_response(fallback_payload),
                usage_details=normalize_usage(fallback_payload.get("usage")),
                metadata=success_metadata,
            )
            return fallback_payload

    def complete_openai_chat(
        self,
        payload: dict[str, Any],
        default_system_instructions: str,
        *,
        route_policy: str = ROUTE_POLICY_MANAGED_AUTO,
        agent_slug: str | None = None,
        context_id: str | None = None,
        trace_metadata_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("Expected non-empty 'messages' list")
        model = self._select_model_for_route(payload.get("model"), route_policy=route_policy)
        instructions = build_instructions(messages, default_system_instructions)
        input_items = openai_messages_to_codex_input(messages)
        codex_tools = openai_tools_to_codex(payload.get("tools"), payload.get("tool_choice"))
        temperature = payload.get("temperature")
        if temperature is not None:
            temperature = float(temperature)
        response = self.complete(
            instructions=instructions,
            input_items=input_items,
            tools=codex_tools,
            session_id=None,
            cancel_event=None,
            model=model,
            temperature=temperature,
            route_policy=route_policy,
            agent_slug=agent_slug,
            context_id=context_id,
            trace_metadata_overrides=trace_metadata_overrides,
        )
        return build_chat_completion_response(response=response, model=model)


CodexOAuthTransport = UnifiedLLMRouter
