"""Telegram events service documentation."""

# Telegram Events Service

`core.telegram_events` is a standalone service that listens to Telegram messages and forwards them to the secretary agent as non-thread events.

> Historical note: the old standalone `telegram-mcp` service has been removed from the active stack. Its outbound Telegram send responsibility now lives in the `better-telegram-mcp` relay, while `telegram-events` only keeps the Telegram authentication needed for listening.

## Responsibilities

- Connect to Telegram using the Telethon user-bot library
- Listen for incoming messages
- Format messages into event payloads
- Forward events to the secretary agent via HTTP
- Preserve archival context for the removed `telegram-mcp` service without treating it as active runtime

## Architecture

The service does NOT use the thread-based flow. Messages are forwarded as standalone events to the secretary agent's `/event` endpoint, and any Telegram reply sending now happens through the `better-telegram-mcp` relay instead of a deleted standalone `telegram-mcp` container.

## Configuration

Environment variables:

- `TELEGRAM_API_ID` - Telegram API ID (required)
- `TELEGRAM_API_HASH` - Telegram API Hash (required)
- `TELEGRAM_SESSION_STRING` - Session string for persistent auth when listening; outbound sending is handled by the `better-telegram-mcp` relay
- `TELEGRAM_SESSION_FILE` - Path to session file (optional, default: sessions/telegram.session)
- `SECRETARY_URL` - Secretary agent HTTP endpoint (default: http://secretary:8787)
- `LOG_LEVEL` - Logging level (default: INFO)

## Running

```bash
python -m core.telegram_events.service_main
```

## Archived telegram-mcp context

The previous operator flow used a standalone `telegram-mcp` container for outbound Telegram replies. That service is no longer part of the supported stack and should be treated as archived reference material only.

Current deployments should use the `better-telegram-mcp` relay for reply delivery.

## Docker

The service runs as a standalone container in docker-compose.yml:

```yaml
telegram-events:
  build: .
  image: orchestra-threads:local
  container_name: telegram-events
  depends_on:
    - orchestra-agents
  environment:
    TELEGRAM_API_ID: ${TELEGRAM_API_ID}
    TELEGRAM_API_HASH: ${TELEGRAM_API_HASH}
    TELEGRAM_SESSION_STRING: ${TELEGRAM_SESSION_STRING}
    TELEGRAM_SESSION_FILE: ${TELEGRAM_SESSION_FILE}
    SECRETARY_URL: http://secretary:8787
  volumes:
    - ./sessions:/app/sessions
  command:
    - python
    - -m
    - core.telegram_events.service_main
```

## Authentication Flow

On first run without a session:
1. Service will prompt for phone number and code
2. After successful auth, it prints the session string
3. Save the session string to `TELEGRAM_SESSION_STRING` in .env if you want a persistent listener session
4. Restart the service - it will use the saved session

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
