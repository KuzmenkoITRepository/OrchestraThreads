# Telegram MCP Server

Thin HTTP proxy MCP server for Telegram messaging.  Proxies `send_telegram_message` tool calls to `telegram-events` service via `POST /send`.

**No Telethon dependency** — all Telegram API access happens through the shared Telethon client in `telegram-events`.

## Architecture

```
agent (SGR in-process / stdio subprocess)
  → TelegramMCPServer.handle_tools_call()
    → TelegramHTTPClient.send_message()
      → POST http://telegram-events:8787/send
        → shared Telethon client
```

## MCP Surface

### Tools

| Tool | Description |
|------|-------------|
| `send_telegram_message` | Send a text message to a configured recipient |

### send_telegram_message

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | yes | Message text (max 4096 chars) |
| `recipient` | string | no | Recipient alias (default: `ivan`) |

Returns: `{ok, message_id, chat_id, recipient}` wrapped in MCP structured content.

## Configuration

Required environment variables:
- `TELEGRAM_EVENTS_URL` — URL of telegram-events HTTP server (e.g. `http://telegram-events:8787`)
- `TELEGRAM_CHAT_ID_IVAN` — Chat ID for recipient "ivan"

Optional:
- `TELEGRAM_DEFAULT_RECIPIENT` — Default alias (default: `ivan`)
- `LOG_LEVEL` — Logging level (default: `INFO`)

## Integration

### SGR in-process (secretary manifest)

```yaml
mcp_servers:
  - name: send_telegram_message
    module: telegram_mcp.mcp_server
    class: TelegramMCPServer
    schema_fn: telegram_tool_definitions
```

### Subprocess (stdio MCP)

```yaml
mcp_servers:
  - name: telegram
    command: python
    args: [-m, telegram_mcp]
    env:
      TELEGRAM_EVENTS_URL: "{env.TELEGRAM_EVENTS_URL}"
      TELEGRAM_CHAT_ID_IVAN: "{env.TELEGRAM_CHAT_ID_IVAN}"
```

## Module Structure

| File | Role |
|------|------|
| `mcp_server.py` | Server class + SGR compat + stdio loop |
| `mcp_dispatch.py` | JSON-RPC method routing |
| `mcp_send.py` | send_telegram_message handler |
| `mcp_payloads.py` | Tool specs and text helpers |
| `mcp_protocol.py` | JSON-RPC envelope builders |
| `mcp_transport.py` | Stdio framing (content-length + newline) |
| `telegram_client.py` | httpx-based HTTP client to telegram-events |
| `config.py` | Environment-backed configuration |
