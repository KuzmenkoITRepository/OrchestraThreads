# Telegram MCP Server

MCP server for Telegram messaging via Telethon (user account).  Shares auth with `telegram_events`.

## MCP Surface

### Tools

| Tool | Description |
|------|-------------|
| `send_telegram_message` | Send text, formatted, reply, or media message |
| `edit_telegram_message` | Edit a previously sent message |
| `delete_telegram_message` | Delete a previously sent message |
| `send_telegram_message_batch` | Send same message to multiple recipients |
| `get_telegram_chat_info` | Get chat/user metadata (cached, TTL 5 min) |
| `check_telegram_read_receipt` | Best-effort read-receipt hint (non-authoritative) |
| `upsert_recipient` | Add or update a recipient alias at runtime |
| `remove_recipient` | Remove a recipient alias at runtime |

### Resources

| URI | Description |
|-----|-------------|
| `telegram://recipients` | Dynamic recipient registry (alias → chat_id) |
| `telegram://rate_limits` | Current rate-limit state |

### Resource Templates

| URI Template | Description |
|--------------|-------------|
| `telegram://thread/{thread_id}/messages` | Messages linked to an orchestra thread |
| `telegram://chat/{recipient}/info` | Cached chat metadata for a recipient alias |

## Tool Details

### send_telegram_message

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | yes | Message text (max 4096 chars) |
| `recipient` | string | no | Recipient alias (default: env default) |
| `parse_mode` | string | no | `"markdown"` or `"html"` |
| `reply_to_message_id` | integer | no | Message ID to reply to |
| `media` | object | no | `{type, data?, path?, filename?}` — photo/document/voice |
| `thread_id` | string | no | Opaque thread ID for metadata linkage |

### edit_telegram_message

| Parameter | Type | Required |
|-----------|------|----------|
| `message_id` | integer | yes |
| `new_text` | string | yes |
| `recipient` | string | no |

### delete_telegram_message

| Parameter | Type | Required |
|-----------|------|----------|
| `message_id` | integer | yes |
| `recipient` | string | no |

### send_telegram_message_batch

| Parameter | Type | Required |
|-----------|------|----------|
| `message` | string | yes |
| `recipients` | string[] | yes |
| `thread_id` | string | no |

### get_telegram_chat_info

| Parameter | Type | Required |
|-----------|------|----------|
| `recipient` | string | yes |

Returns: `{chat_id, chat_type, title, username, first_name, last_name, is_bot, fetched_at}`

### check_telegram_read_receipt

| Parameter | Type | Required |
|-----------|------|----------|
| `message_id` | integer | yes |
| `recipient` | string | no |

Returns: `{message_id, chat_id, probably_read, checked_at, disclaimer}`

**Note:** Read receipts are best-effort only.  Telegram does not guarantee read-receipt accuracy, especially in group chats.

## Configuration

Required environment variables:
- `TELEGRAM_API_ID` — Telegram API ID
- `TELEGRAM_API_HASH` — Telegram API Hash
- `TELEGRAM_SESSION_STRING` — Telethon session string
- `TELEGRAM_CHAT_ID_IVAN` — Chat ID for recipient "ivan"

Optional:
- `TELEGRAM_CHAT_ID_*` — Additional recipients (`TELEGRAM_CHAT_ID_BOB`, etc.)
- `TELEGRAM_DEFAULT_RECIPIENT` — Default alias (default: `ivan`)
- `TELEGRAM_TIMEOUT_SECONDS` — Timeout (default: `10.0`)
- `TELEGRAM_MAX_RETRIES` — Retries (default: `3`)
- `TELEGRAM_STORE_PATH` — SQLite store file (default: `telegram_mcp_messages.db`)
- `TELEGRAM_RECIPIENTS_FILE` — JSON file for persistent recipient registry
- `LOG_LEVEL` — Logging level (default: `INFO`)

## Integration

```yaml
mcp_servers:
  telegram:
    command: python
    args: [-m, telegram_mcp]
    env:
      TELEGRAM_API_ID: ${TELEGRAM_API_ID}
      TELEGRAM_API_HASH: ${TELEGRAM_API_HASH}
      TELEGRAM_SESSION_STRING: ${TELEGRAM_SESSION_STRING:-}
      TELEGRAM_CHAT_ID_IVAN: ${TELEGRAM_CHAT_ID_IVAN}
```

## Testing

```bash
PYTHONPATH=src python -m pytest src/telegram_mcp/tests/ -v
```
