# Langfuse Integration Plan

## Goal

Add Langfuse tracing inside `llm_proxy` and group requests by the stable agent context:

- `agent_slug`
- `context_id`

`thread_id`, `user_id`, and incoming app-level session ids are not used as the primary grouping key.

## Current State

- `orchestra` already sends `X-Orchestra-Agent-Slug` and `X-Orchestra-Context-Id` to `llm_proxy`.
- `llm_proxy` already extracts this metadata in `service.py`.
- `router.py` currently discards that metadata and does not emit any Langfuse traces.

## Grouping Model

Source of truth inside the system:

- `agent_slug`
- `context_id`

Langfuse projection:

- `session_id = "{agent_slug}:{context_id}"`

This preserves the requested business semantics while using Langfuse's native grouping capabilities.

## Implementation Steps

1. Add a dedicated telemetry layer under `src/core/llm_proxy/langfuse.py`.
2. Extend `ProxyConfig` and `service_main.py` with Langfuse settings.
3. Keep using the existing agent-side headers, without changing the agent contract.
4. Create one root Langfuse trace per `llm_proxy` request.
5. Create one child generation per actual upstream attempt:
   - Codex profile attempt
   - OpenAI-compatible fallback attempt
6. Propagate only compact request metadata and compact I/O summaries by default.
7. Flush and shut down the Langfuse client on service cleanup.
8. Add automated tests for grouping, fallback, and error paths.
9. Run manual smoke tests with real `thread CLI` traffic and verify that requests sharing the same `agent_slug + context_id` land in the same Langfuse group.

## Files To Change

- `src/core/llm_proxy/langfuse.py`
- `src/core/llm_proxy/service.py`
- `src/core/llm_proxy/router.py`
- `src/core/llm_proxy/service_main.py`
- `src/core/llm_proxy/docs/README.md`
- `src/core/llm_proxy/tests/test_service.py`
- `requirements.txt`
- `docker-compose.yml`
- `.env.example`

## Defaults

- tracing disabled by default unless explicitly enabled
- grouping only by `agent_slug + context_id`
- no `user_id`
- no `thread_id`-based grouping
- compact summaries instead of full prompts by default

## Validation

Automated:

- `docker compose --profile test run --rm test`

Manual:

- start stack with Langfuse-enabled `llm_proxy`
- send multiple requests through `thread CLI` into the same agent context
- confirm identical Langfuse `session_id`
- clear context
- confirm a new Langfuse `session_id` is used
