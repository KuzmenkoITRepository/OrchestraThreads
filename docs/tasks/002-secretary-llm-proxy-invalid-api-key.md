## BUG-002: Secretary Telegram flow fails with 500 because OmniRoute auth returns `401 Invalid API key`

### Summary

After the Telegram event handling fix, the `secretary` agent now receives and starts processing `telegram_message` events, but the flow still fails before any reply is sent. The failure has moved deeper into the stack:

- Telegram message is received
- `telegram-events` forwards to `events-engine`
- `events-engine` delivers to `secretary`
- `secretary` starts SGR event processing
- the SGR LLM client calls the configured OmniRoute endpoint
- that endpoint returns `401 Invalid API key`
- `secretary` returns HTTP 500 from `/event`
- `events-engine` returns HTTP 500 to `telegram-events`
- no Telegram reply is sent

This is a runtime/auth configuration failure in the direct LLM path, not an event-kind routing failure.

### Severity

Critical — end-to-end Telegram interaction is still blocked.

### Reproduction case

Environment at time of failure:

- full docker stack up and healthy
- required agents started: `secretary`, `orchestra`, `dev`, `qa`, `devops`
- `secretary` backend: `sgr_minimax`

Reproduction steps:

1. Start the stack
2. Start the `secretary` agent
3. Send a Telegram message to the bot (example used: `Привет! Ответь мне в телеграмме...`)
4. Observe: no response in Telegram

### Observed behavior

The request path reaches the `secretary` agent, but the agent crashes while calling the OmniRoute-backed LLM endpoint.

### Expected behavior

`secretary` should complete the LLM call and respond through the configured Telegram MCP tool.

### Logs and evidence

#### 1. Telegram ingress receives the user message

Source: `docker logs orchestrathreads-telegram-events-1 --tail 120`

```text
2026-04-07 13:27:00,866 INFO core.telegram_events.listener: Received message from Иван in Иван: Привет! Ответь мне в телеграмме...
2026-04-07 13:27:00,866 INFO core.telegram_events.service: Forwarding message to events-engine: http://events-engine:8789/deliver
2026-04-07 13:27:00,971 INFO httpx: HTTP Request: POST http://events-engine:8789/deliver "HTTP/1.1 500 Internal Server Error"
2026-04-07 13:27:00,972 ERROR core.telegram_events.service: Failed to forward message to events-engine: status=500, body={"success": false, "error": "Failed to deliver event to agent"}
```

#### 2. Events engine delivers to secretary, but secretary returns 500

Source: `docker logs orchestrathreads-events-engine-1 --tail 120`

```text
2026-04-07 13:27:00,880 INFO core.events_engine.service: Delivering event to agent: secretary
2026-04-07 13:27:00,935 INFO core.events_engine.service: Delivering event to: http://orchestra-agent-secretary:8787/event
2026-04-07 13:27:00,970 ERROR core.events_engine.service: Failed to deliver event to http://orchestra-agent-secretary:8787: status=500, body=500 Internal Server Error

Server got itself in trouble
2026-04-07 13:27:00,971 INFO aiohttp.access: 172.20.0.15 [07/Apr/2026:13:27:00 +0000] "POST /deliver HTTP/1.1" 500 241 "-" "python-httpx/0.28.1"
```

#### 3. Secretary actually starts processing the Telegram event

Source: `docker logs orchestra-agent-secretary --tail 200`

```text
2026-04-07 13:27:00,937 INFO agents.sgr.agent_runtime.event_routing: Processing SGR event telegram_message (telegram_message)
```

This confirms BUG-001 was at least partially addressed: `telegram_message` is now considered actionable.

#### 4. Secretary crashes on OmniRoute authentication

Source: `docker logs orchestra-agent-secretary --tail 200`

```text
2026-04-07 13:27:00,967 ERROR aiohttp.server: Error handling request from 172.20.0.13
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 517, in _handle_request
    resp = await request_handler(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
    return await handler(request)
           ^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/src/core/orchestra_agents/runtime/app.py", line 35, in event
    return web.json_response((await self.backend.handle_events(delivery)).to_dict())
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/backend.py", line 75, in handle_events
    return await _routing.handle_events(self, delivery)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/event_routing.py", line 39, in handle_events
    return await _process_events(backend, delivery, pending)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/event_routing.py", line 52, in _process_events
    await _process_next_event(backend, delivery, aggregate, state, remaining)
  File "/workspace/agents/sgr/agent_runtime/event_routing.py", line 71, in _process_next_event
    state.last_peer = await _process_event(backend, delivery, event, event_id, aggregate)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/event_routing.py", line 88, in _process_event
    outcome = await _loop.run_turn(backend, delivery, event, session_key, peer)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/event_loop.py", line 29, in run_turn
    should_stop, retries = await _run_step(
                           ^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/event_loop.py", line 51, in _run_step
    await backend._llm.chat_completion(_chat_payload(backend, messages, event)),
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/agents/sgr/agent_runtime/llm_client.py", line 52, in chat_completion
    raise RuntimeError(f"omniroute chat request failed: HTTP {response.status}: {raw}")
RuntimeError: omniroute chat request failed: HTTP 401: {"error":{"message":"Invalid API key","type":"authentication_error","code":"invalid_api_key"}}
2026-04-07 13:27:00,970 INFO aiohttp.access: 172.20.0.13 [07/Apr/2026:13:27:00 +0000] "POST /event HTTP/1.1" 500 246 "-" "Python/3.11 aiohttp/3.13.5"
```

#### 5. OmniRoute auth confirms 401 failure

Source: `docker logs orchestrathreads-orchestra-omniroute-1 --tail 120`

```text
2026-04-07 13:27:00,967 ERROR aiohttp.server: Error handling request from 172.20.0.13
RuntimeError: omniroute chat request failed: HTTP 401: {"error":{"message":"Invalid API key","type":"authentication_error","code":"invalid_api_key"}}
```

### Relevant config snapshot

Source: `agents/secretary/manifest.yaml`

```yaml
runtime:
  env:
    OMNIROUTE_URL: http://orchestra-omniroute:20128
    OMNIROUTE_API_KEY: ${OMNIROUTE_API_KEY}

backend:
  type: sgr_minimax
  config:
    route_policy: minimax_only
    model: minimax/MiniMax-M2.7
```

### Likely root cause

The `secretary` SGR runtime is now reaching OmniRoute, but the credential sent to the runtime endpoint is rejected.

Possible reasons:

1. The runtime sent an invalid placeholder credential instead of `OMNIROUTE_API_KEY`.
2. The SGR LLM client is sending the wrong auth header format.
3. The other fix changed manifest/runtime structure, but the actual auth contract expected by OmniRoute was not updated.
4. The runtime may now be pointing at a different OmniRoute auth mode than the previous agent-mux path.

### Fix direction

Investigate and align the auth contract between:

- `agents/sgr/agent_runtime/llm_client.py`
- `agents/secretary/manifest.yaml`
- current OmniRoute auth expectations
- current runtime API key expectations

Specifically verify:

1. what header `SGRLLMClient` sends to `OMNIROUTE_URL`
2. whether `OMNIROUTE_API_KEY` is passed into that client and used correctly
3. whether the runtime endpoint expects a real `OMNIROUTE_API_KEY`
4. whether the configured direct OmniRoute model path matches the working Minimax setup

### Current state after failure

Stack status remained healthy during the incident:

```text
orchestrathreads-events-engine-1         Up 4 minutes (healthy)
orchestrathreads-langfuse-1              Up 4 minutes (healthy)
orchestrathreads-langfuse-postgres-1     Up 4 minutes (healthy)
orchestrathreads-orchestra-agents-1      Up 4 minutes (healthy)
orchestrathreads-orchestra-omniroute-1   Up 4 minutes (healthy)
orchestrathreads-orchestra-threads-1     Up 4 minutes (healthy)
orchestrathreads-postgres-1              Up 4 minutes (healthy)
orchestrathreads-scheduler-cron-1        Up 4 minutes (healthy)
orchestrathreads-task-registry-1         Up 4 minutes (healthy)
orchestrathreads-telegram-events-1       Up 3 minutes (healthy)
orchestrathreads-telegram-mcp-1          Up 4 minutes (healthy)
```

### Relationship to BUG-001

This is a follow-up failure after the previous `telegram_message` routing issue:

- BUG-001: event dropped before processing
- BUG-002: event processed, but OmniRoute auth fails
