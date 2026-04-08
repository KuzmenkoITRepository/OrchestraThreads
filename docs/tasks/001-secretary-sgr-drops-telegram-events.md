# BUG-001: Secretary SGR backend silently drops telegram_message events

**Date:** 2026-04-07
**Severity:** Critical
**Component:** `agents/sgr/agent_runtime/event_routing.py`
**Affected agent:** `secretary` (after migration to `sgr_minimax` backend)

## Summary

After converting the `secretary` agent from `agent_mux` to `sgr_minimax` backend, the agent silently drops all Telegram messages. The full delivery chain works (Telegram → telegram-events → events-engine → secretary `/event` → 200 OK), but the SGR backend discards the event as "not actionable" and never invokes the LLM or any MCP tools.

## Root Cause

`agents/sgr/agent_runtime/event_routing.py`, function `_is_actionable()` (line ~122):

```python
def _is_actionable(event: Any, settings: SGRRuntimeSettings) -> bool:
    if event.event_kind == "message":
        return bool(event.requires_response)
    if event.event_kind == "notification":
        return bool(normalize_optional_str(event.notification_status))
    if event.event_kind == "inactive":
        return settings.react_to_inactive
    return False  # <-- telegram_message falls here
```

Telegram events are delivered with `event_kind: "telegram_message"` (set in `src/core/telegram_events/service.py:168`). This kind is not in the SGR whitelist, so `_is_actionable()` returns `False` and the event is silently discarded via `_results.no_action_result()`.

By contrast, the `agent_mux` backend has no such filter — it accepts all event kinds.

## Reproduction Steps

1. Start the full stack: `docker compose up --build -d`
2. Start secretary agent: `curl -X POST http://127.0.0.1:8790/api/v1/agents/secretary/start`
3. Send a Telegram message to the bot
4. Observe: no response from secretary

## Evidence

### telegram-events log (message received and forwarded)
```
2026-04-07 11:50:08,093 INFO core.telegram_events.listener: Received message from Иван in Иван: Привет! Ответь мне в телеграмме...
2026-04-07 11:50:08,093 INFO core.telegram_events.service: Forwarding message to events-engine: http://events-engine:8789/deliver
2026-04-07 11:50:08,153 INFO httpx: HTTP Request: POST http://events-engine:8789/deliver "HTTP/1.1 200 OK"
2026-04-07 11:50:08,154 INFO core.telegram_events.service: Successfully forwarded message 5526 to events-engine
```

### events-engine log (delivered to secretary successfully)
```
2026-04-07 11:50:08,103 INFO core.events_engine.service: Delivering event to agent: secretary
2026-04-07 11:50:08,149 INFO core.events_engine.service: Delivering event to: http://orchestra-agent-secretary:8787/event
2026-04-07 11:50:08,151 INFO core.events_engine.service: Successfully delivered event to http://orchestra-agent-secretary:8787
```

### secretary log (accepted HTTP request, no processing)
```
2026-04-07 11:50:08,151 INFO aiohttp.access: 172.20.0.12 [07/Apr/2026:11:50:08 +0000] "POST /event HTTP/1.1" 200 341 "-" "Python/3.11 aiohttp/3.13.5"
```
No further log lines — no LLM call, no MCP tool invocation, no error.

### Additional context
- Secretary was previously on `agent_mux` backend (which handles all event_kind values without filtering)
- SGR backend was originally designed for the `sgr` example agent which only receives thread-based events (`message`, `notification`, `inactive`)
- Secretary needs to handle non-thread events like `telegram_message`

## Proposed Fix

Extend `_is_actionable()` in `agents/sgr/agent_runtime/event_routing.py` to handle `telegram_message` events:

```python
def _is_actionable(event: Any, settings: SGRRuntimeSettings) -> bool:
    if event.event_kind == "message":
        return bool(event.requires_response)
    if event.event_kind == "notification":
        return bool(normalize_optional_str(event.notification_status))
    if event.event_kind == "inactive":
        return settings.react_to_inactive
    if event.event_kind == "telegram_message":
        return True
    return False
```

Alternatively, consider making SGR use an allowlist approach or treating unknown event_kinds as actionable by default (matching agent_mux behavior).

## Secondary Issue

Secretary agent shows `online: false` in orchestra-threads agent registry (stale `last_seen_at` from 2026-04-03). This means heartbeat/registration is also not working — likely because the SGR backend only registers when it gets a thread-based event (see `_resolve_context()` → `ensure_registered()` which is only called for events with `thread_id`). Registration should happen on startup, not on first thread event.
