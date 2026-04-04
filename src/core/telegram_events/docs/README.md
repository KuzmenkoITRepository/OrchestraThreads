"""Telegram events service documentation."""

# Telegram Events Service

`core.telegram_events` is a standalone service that listens to Telegram messages and forwards them to the secretary agent as non-thread events.

## Responsibilities

- Connect to Telegram using Telethon user-bot library
- Listen for incoming messages
- Format messages into event payloads
- Forward events to secretary agent via HTTP

## Architecture

The service does NOT use the thread-based flow. Messages are forwarded as standalone events to the secretary agent's `/event` endpoint.

## Configuration

Environment variables:

- `TELEGRAM_API_ID` - Telegram API ID (required)
- `TELEGRAM_API_HASH` - Telegram API Hash (required)
- `TELEGRAM_SESSION_STRING` - Session string for persistent auth (optional)
- `TELEGRAM_SESSION_FILE` - Path to session file (optional, default: sessions/telegram.session)
- `SECRETARY_URL` - Secretary agent HTTP endpoint (default: http://secretary:8787)
- `LOG_LEVEL` - Logging level (default: INFO)

## Running

```bash
python -m core.telegram_events.service_main
```

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
3. Save the session string to `TELEGRAM_SESSION_STRING` in .env
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
