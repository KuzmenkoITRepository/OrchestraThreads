# Telegram MCP Server

MCP server for sending Telegram messages via Telethon (user account).

## Overview

This service exposes a `send_telegram_message` tool that allows agents to send messages to Telegram chats using the same user account (Василий) that telegram-events uses for receiving messages.

## Configuration

Required environment variables:
- `TELEGRAM_API_ID` - Telegram API ID (from https://my.telegram.org)
- `TELEGRAM_API_HASH` - Telegram API Hash (from https://my.telegram.org)
- `TELEGRAM_SESSION_STRING` - Telethon session string (same as telegram-events)
- `TELEGRAM_CHAT_ID_IVAN` - Chat ID for recipient "ivan"

Optional environment variables:
- `TELEGRAM_DEFAULT_RECIPIENT` - Default recipient alias (default: `ivan`)
- `TELEGRAM_TIMEOUT_SECONDS` - Connection timeout in seconds (default: `10.0`)
- `TELEGRAM_MAX_RETRIES` - Max retry attempts (default: `3`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## Usage

The MCP server runs over stdio and exposes one tool:

### send_telegram_message

Send a text message to a Telegram chat.

**Parameters:**
- `message` (required): Message text to send (max 4096 characters)
- `recipient` (optional): Recipient alias (default: "ivan")

**Returns:**
- On success: `{"ok": true, "message_id": 12345, "chat_id": 123456789, "recipient": "ivan"}`
- On failure: `{"ok": false, "error": "Error description", "error_code": 400}`

## Integration

Add to agent manifest:

```yaml
mcp_servers:
  telegram:
    command: python
    args:
      - -m
      - telegram_mcp
    env:
      TELEGRAM_API_ID: ${TELEGRAM_API_ID}
      TELEGRAM_API_HASH: ${TELEGRAM_API_HASH}
      TELEGRAM_SESSION_STRING: ${TELEGRAM_SESSION_STRING:-}
      TELEGRAM_CHAT_ID_IVAN: ${TELEGRAM_CHAT_ID_IVAN}
      LOG_LEVEL: INFO
```

## Testing

Run unit tests:
```bash
cd /home/odinykt/projects/OrchestraThreads
PYTHONPATH=src python -m unittest discover -s src/telegram_mcp/tests -v
```
