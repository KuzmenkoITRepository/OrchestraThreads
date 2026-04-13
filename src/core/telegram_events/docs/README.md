# Telegram Events Service

`core.telegram_events` is a standalone ingress service that receives Telegram messages and forwards them to the secretary agent as non-thread events. The current runtime is relay-based: the service consumes the `better-telegram-mcp` server as an SSE client, and outbound Telegram sending happens through the relay’s HTTP MCP surface.

## Responsibilities

- Consume Telegram updates from the `better-telegram-mcp` relay over SSE
- Format incoming messages into event payloads
- Forward events to the secretary agent via HTTP
- Send Telegram replies through the relay’s `/mcp` endpoint when needed

## Architecture

The service no longer treats a Telethon listener session as the primary runtime model. Instead, `telegram-events` runs as an SSE consumer against `better-telegram-mcp`, which handles Telegram transport and exposes two integration points:

- `BETTER_TELEGRAM_MCP_EVENTS_URL` for the SSE event stream
- `BETTER_TELEGRAM_MCP_URL` for MCP calls, including sending messages through `/mcp`

Incoming Telegram updates are converted into the same event payloads the secretary expects. When the service needs to send a Telegram reply, it calls the relay’s HTTP MCP endpoint rather than talking to Telegram directly.

## Configuration

Environment variables:

- `TELEGRAM_API_ID` - Telegram API ID (required by the relay)
- `TELEGRAM_API_HASH` - Telegram API Hash (required by the relay)
- `TELEGRAM_SESSION_STRING` - Session string used by the relay for Telegram auth when present
- `BETTER_TELEGRAM_MCP_URL` - Relay MCP endpoint, usually `http://better-telegram-mcp:3000/mcp`
- `BETTER_TELEGRAM_MCP_EVENTS_URL` - Relay SSE events endpoint, usually `http://better-telegram-mcp:3000/events/telegram`
- `BETTER_TELEGRAM_MCP_TOKEN` - Bearer token required by the relay
- `SECRETARY_URL` - Secretary agent HTTP endpoint (default: `http://secretary:8787`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## Running

Start the service with the main application entry point:

```bash
python -m core.telegram_events.service_main
```

In Docker Compose, `telegram-events` depends on `better-telegram-mcp` and `events-engine`:

```yaml
telegram-events:
  build: .
  image: orchestra-threads:${OT_TAG:-local}
  depends_on:
    better-telegram-mcp:
      condition: service_healthy
    events-engine:
      condition: service_healthy
  environment:
    PYTHONPATH: /app/src
    BETTER_TELEGRAM_MCP_URL: ${BETTER_TELEGRAM_MCP_URL:-http://better-telegram-mcp:3000/mcp}
    BETTER_TELEGRAM_MCP_EVENTS_URL: ${BETTER_TELEGRAM_MCP_EVENTS_URL:-http://better-telegram-mcp:3000/events/telegram}
    BETTER_TELEGRAM_MCP_TOKEN: ${BETTER_TELEGRAM_MCP_TOKEN:-}
    TELEGRAM_EVENTS_HTTP_HOST: 0.0.0.0
    TELEGRAM_EVENTS_HTTP_PORT: "8787"
    EVENTS_ENGINE_URL: http://events-engine:8789
    TARGET_AGENT_SLUG: ${TARGET_AGENT_SLUG:-secretary}
    LOG_LEVEL: ${LOG_LEVEL:-INFO}
  command:
    - python
    - -m
    - core.telegram_events.service_main
```

## Service startup flow

1. Load relay and secretary configuration from environment variables.
2. Create an `SSEConsumer` for `BETTER_TELEGRAM_MCP_EVENTS_URL`.
3. Start consuming Telegram events from `better-telegram-mcp`.
4. Forward each update to the secretary agent through the HTTP event pipeline.
5. Use `BETTER_TELEGRAM_MCP_URL` with `/mcp` when a send operation is required.

## Event Format

Events sent to secretary:

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

## Archived telegram-mcp context

The previous operator flow used a standalone `telegram-mcp` container for direct outbound Telegram replies. That service is no longer part of the supported stack.

For historical reference only:

- the old listener-centric model used Telethon as the primary runtime
- outbound Telegram sending used to be handled by the removed `telegram-mcp` container
- current deployments should use the `better-telegram-mcp` relay for both SSE consumption and `/mcp` send operations
