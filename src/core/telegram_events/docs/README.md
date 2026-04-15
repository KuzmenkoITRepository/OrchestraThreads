# Telegram Events Service

`core.telegram_events` is the ingress bridge for Telegram updates. It accepts agent registration, opens SSE consumers only for registered MCP URLs, and routes inbound events through the registry. Outbound agent messages go directly to `telegram-mcp` through MCP, outside this service.

## Responsibilities

- Accept internal `/register` calls from agent runtime
- Create or reuse an SSE consumer for each registered Telegram MCP URL
- Route inbound updates by registry slug through `events-engine`
- Drop or log updates from unknown source MCP URLs
- Keep Telegram outbound flow on direct MCP calls from agents to `telegram-mcp`

## Architecture

`telegram-events` no longer runs as a single startup SSE listener with one fixed target. Runtime starts with zero Telegram consumers. When an agent registers, the service records its slug, normalized MCP URL, and routing metadata in an in-memory registry, then creates a consumer for that URL at `{telegram_mcp_url}/events/telegram`.

Registration is internal and unauthenticated. Success returns `{"ok": True}`. Duplicate registration with same slug and same normalized MCP URL is accepted. Same slug with a new MCP URL remaps the consumer. Different slug with same normalized MCP URL is a conflict and returns `409`.

Inbound Telegram updates are mapped to the registered slug for that source MCP URL, then forwarded through `events-engine`. Outbound replies are handled by the agent itself through `telegram-mcp` MCP, so this service only owns inbound routing.

## Configuration

Environment variables currently relevant to this service:

- `TELEGRAM_EVENTS_HTTP_HOST`, host for internal HTTP service, usually `0.0.0.0`
- `TELEGRAM_EVENTS_HTTP_PORT`, port for internal HTTP service, usually `8787`
- `EVENTS_ENGINE_URL`, routing endpoint for outbound event delivery, usually `http://events-engine:8789`
- `LOG_LEVEL`, logging level, default `INFO`

Telegram API credentials and relay-specific send settings are owned by `telegram-mcp` or other upstream components, not by this service docs.

## Running

Start the service with the main application entry point:

```bash
python -m core.telegram_events.service_main
```

In Docker Compose, `telegram-events` depends on `events-engine` and exposes its own internal HTTP listener:

```yaml
telegram-events:
  build: .
  image: orchestra-threads:${OT_TAG:-local}
  depends_on:
    events-engine:
      condition: service_healthy
  environment:
    PYTHONPATH: /app/src
    TELEGRAM_EVENTS_HTTP_HOST: 0.0.0.0
    TELEGRAM_EVENTS_HTTP_PORT: "8787"
    EVENTS_ENGINE_URL: http://events-engine:8789
    LOG_LEVEL: ${LOG_LEVEL:-INFO}
  command:
    - python
    - -m
    - core.telegram_events.service_main
```

## Service startup flow

1. Start internal HTTP surface and shared runtime clients.
2. Wait for `/register` calls from agent runtime.
3. Normalize incoming MCP URL and record slug to URL mapping in registry.
4. Create SSE consumer for `{telegram_mcp_url}/events/telegram` for each registration.
5. Route incoming updates by registry lookup on source MCP URL.
6. Forward matched events through `events-engine`.
7. Leave outbound Telegram sending to agent runtime via direct MCP calls to `telegram-mcp`.

## Event Format

Events sent through `events-engine` keep Telegram source metadata and registry-derived routing context.

```json
{
  "prompt": "New Telegram message received:\nFrom: John Doe\nUsername: @johndoe\nChat: John Doe\nTime: 2026-04-03T18:27:00\n\nMessage:\nHello, assistant!",
  "metadata": {
    "source": "telegram",
    "chat_id": "123456789",
    "message_id": 42,
    "sender_name": "John Doe",
    "username": "johndoe",
    "user_id": "123456789",
    "timestamp": "2026-04-03T18:27:00"
  }
}
```

## Notes

- Internal registration uses registry outcomes `REGISTERED`, `DUPLICATE`, `REMAPPED`, and `CONFLICT`.
- Unknown source MCP URLs are ignored after logging.
- `telegram-events` owns inbound routing only. Direct Telegram send path stays in agent runtime through `telegram-mcp` MCP.
