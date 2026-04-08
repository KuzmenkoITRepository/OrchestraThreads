# BUG-003: Second Telegram message never reaches the system — Telethon session conflict

## Summary

The first Telegram message is processed successfully: secretary receives the event, calls the LLM, and replies via `send_telegram_message`. However, **every subsequent message from the user is silently lost** — `telegram-events` listener never logs receiving it. The Telegram client inside the listener appears to go deaf after the first successful round-trip.

## Severity

Critical — only the first message in each session gets a response. Multi-turn conversation is impossible.

## Root Cause

Two independent Telethon clients share the same `TELEGRAM_SESSION_STRING`:

1. **`telegram-events`** service — runs a persistent `TelegramClient` listening for incoming (and outgoing) messages.
2. **`secretary` agent** — creates a **new** `TelegramClient` inside the `send_telegram_message` MCP tool call every time it needs to reply.

When the second client (`secretary` → `telegram_mcp`) connects with the same session string, Telegram's MTProto protocol **invalidates or disrupts the first client's connection**. Telethon does not always raise an explicit error for this — the listener simply stops receiving updates.

### Evidence chain

#### First message — full success
```
16:25:09 telegram-events: Received message from Иван
16:25:09 secretary: Processing SGR event telegram_message
16:25:12 secretary: Executing SGR tool call send_telegram_message
16:25:12 secretary (telegram_mcp): Starting Telegram client...          ← SECOND CLIENT CONNECTS
16:25:13 secretary (telegram_mcp): Logged in as: Василий (ID: 7282819104)
16:25:14 secretary (telegram_mcp): Telegram message sent successfully
16:25:14 secretary: POST /event 200
```

#### After reply — listener goes silent
```
16:25:28 secretary: GET /healthz 200
16:25:58 secretary: GET /healthz 200
... only healthchecks, no more "Received message" entries ...
```

`telegram-events` full log after the first message: **zero** additional "Received" entries. The user's second message never appears.

#### Telethon session string reuse confirmed
Both services use the same session:
- `telegram-events` env: `TELEGRAM_SESSION_STRING` (from docker-compose passthrough)
- `secretary` manifest → `telegram_mcp` MCP server env: `TELEGRAM_SESSION_STRING: "{env.TELEGRAM_SESSION_STRING}"` — same value

### Additional observation: outgoing echo problem

`listener.py:148-149` registers handlers for both `incoming=True` and `outgoing=True`:
```python
client.add_event_handler(self._handle_message, events.NewMessage(incoming=True))
client.add_event_handler(self._handle_message, events.NewMessage(outgoing=True))
```

This means when secretary sends a reply via Telegram, the listener also catches the **outgoing** message and forwards it back to events-engine → secretary as a new event. In the previous session this was visible:

```
15:40:07 secretary: POST /event 200 (358 bytes — duplicate/no_action result)
```

This outgoing echo doesn't cause a crash (SGR dedup catches it), but it's wasted work and could cause unexpected behavior.

## Reproduction Steps

1. Start the full stack and all agents
2. Send first Telegram message → secretary replies successfully
3. Send second Telegram message → no response, no log entry in telegram-events

## Proposed Fix

### Option A: Separate Telegram sessions (recommended)
Generate a second Telegram session string for `telegram_mcp` (the sending client). This way the listener and sender operate on independent sessions and don't interfere.

### Option B: Shared Telegram client
Refactor `telegram_mcp` to not create its own Telethon client. Instead, expose a shared client or use the `telegram-events` service as an outbound proxy too (add a `/send` endpoint).

### Option C: Reconnect-on-disconnect in listener
Add automatic reconnection logic to `telegram-events` listener so it recovers after being displaced. This is a workaround, not a fix — the session conflict would still cause a brief message-loss window.

### Bonus fix: Remove outgoing handler
Remove the `outgoing=True` handler from `listener.py:149` unless there's a specific requirement to listen to the bot's own messages. This eliminates the echo problem.

## Affected Components

- `src/core/telegram_events/listener.py` — victim of session displacement
- `src/telegram_mcp/telegram_client.py` — creates conflicting second client
- `agents/secretary/manifest.yaml` — passes same session string to both

## Relationship to Previous Bugs

- BUG-001: event_kind filtering (fixed)
- BUG-002: LLM proxy auth (fixed)
- BUG-003: session conflict kills listener after first reply (this bug)
