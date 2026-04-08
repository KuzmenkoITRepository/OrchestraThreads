# Telegram MCP Roadmap

**Last Updated:** 2026-04-08
**Status:** Waves 1-5 Complete

## Current State

The `telegram_mcp` module is a full-featured stdio MCP server for Telegram messaging. It uses Telethon (user account) and shares authentication with `telegram_events`.

**Implemented (Waves 1-5 + Oracle fixes):**
- Dynamic recipient registry with env fallback, runtime `upsert_recipient`/`remove_recipient` tools, optional JSON file persistence
- 8 tools: send, edit, delete, batch send, chat info, read receipt, upsert recipient, remove recipient
- Text, markdown, HTML formatting via `parse_mode`
- Reply-to via `reply_to_message_id`
- Media support: photo, document, voice via base64 or local file path
- Thread context: opaque `thread_id` metadata on sends, `telegram://thread/{id}/messages` resource
- Message lifecycle: send → edit → delete with durable SQLite metadata store (file-backed by default)
- Batch send to multiple recipients with per-item results (partial-failure safe)
- Chat info queries with 5-minute TTL cache (`get_telegram_chat_info`), also served via `telegram://chat/{recipient}/info` resource
- Best-effort read receipt hints (`check_telegram_read_receipt`) — non-authoritative
- Rate limit visibility (`telegram://rate_limits` resource) with FloodWait recording
- Retry logic for FloodWait and network errors on both plain and rich send paths
- Config knobs: `TELEGRAM_MAX_RETRIES` and `TELEGRAM_TIMEOUT_SECONDS` applied end-to-end
- Structured error responses

**Remaining limitations:**
- Read receipts are best-effort only (Telegram API constraint)
- No persistent chat-info cache across restarts (in-memory TTL only)
- No Prometheus metrics

## Top 10 Priority Improvements

### 1. Dynamic Recipient Registry — ✅ DONE

Implemented in Waves 1 + Oracle fixes.
Runtime `upsert_recipient`/`remove_recipient` MCP tools, env-variable fallback, optional JSON file persistence via `TELEGRAM_RECIPIENTS_FILE`.

### 2. Media Support — ✅ DONE

Implemented in Wave 2 + Oracle fixes.
Photos, documents, voice via base64 or local file path. Size validation enforced.

### 3. Thread Context Integration — ✅ DONE

Implemented in Wave 4.
Opaque `thread_id` on sends, `telegram://thread/{id}/messages` resource, SQLite-backed metadata.

### 4. Message Formatting — ✅ DONE

Implemented in Wave 2.
Markdown and HTML via `parse_mode` parameter.

### 5. Message Editing and Deletion — ✅ DONE

Implemented in Wave 3.
SQLite-backed store for sent message metadata. `edit_telegram_message` and `delete_telegram_message` tools.

### 6. Batch Operations — ✅ DONE

Implemented in Wave 4 + Oracle fixes.
`send_telegram_message_batch` with `asyncio.gather`, per-recipient results, partial-failure safe.

### 7. Read Receipts — ✅ DONE (best-effort)

Implemented in Wave 5.
`check_telegram_read_receipt` uses `readOutboxMaxId` from Telethon `get_dialogs`. Non-authoritative by design.

### 8. Chat Information Queries — ✅ DONE

Implemented in Wave 5.
`get_telegram_chat_info` tool and `telegram://chat/{recipient}/info` resource with 5-minute TTL cache. Fetch-on-cache-miss.

### 9. Reply Support — ✅ DONE

Implemented in Wave 2.
Optional `reply_to_message_id` on sends. Persisted in message store.

### 10. Rate Limiting — ✅ DONE

Implemented in Wave 1 + retry parity fix.
`telegram://rate_limits` resource exposes `requests_sent`, `flood_wait_until`, `window_start`. FloodWait events from rich sends recorded.

## Implementation Phases

### Q2 2026: Core Enhancements
**Goal:** Make telegram_mcp production-ready for multi-recipient, formatted messaging.

- Dynamic Recipient Registry (4 weeks)
- Message Formatting (1 week)
- Message Editing and Deletion (2 weeks)

**Milestone:** Agents can send formatted messages to any configured recipient and correct mistakes.

### Q3 2026: Rich Media and Context
**Goal:** Enable visual communication and thread integration.

- Media Support (6 weeks)
- Thread Context Integration (3 weeks)
- Read Receipts (1 week)

**Milestone:** Agents can send screenshots, documents, and link messages to orchestra threads.

### Q4 2026: Advanced Operations
**Goal:** Optimize for bulk operations and chat intelligence.

- Batch Operations (2 weeks)
- Chat Information Queries (2 weeks)
- Reply Support (1 week)
- Rate Limiting (1 week)

**Milestone:** Agents can broadcast efficiently, check recipient status, and manage rate limits.

## Technical Debt

### Current Issues
1. **No persistent chat-info cache:** In-memory TTL only; lost on restart. Low priority — re-fetches are cheap.
2. **Telethon session in memory:** Restart loses session state (mitigated by `SESSION_STRING`, but adds startup latency).
3. **No metrics:** Can't track message volume, error rates, or retry frequency without external logging.
4. **No markdown/HTML validation before send:** Telethon parse errors surface at send time, not at tool-call time.

### Resolved
- ~~No persistent message store~~ — SQLite file-backed by default (`TELEGRAM_STORE_PATH`)
- ~~Env-based recipient config doesn't scale~~ — Runtime `upsert_recipient`/`remove_recipient` + optional JSON file
- ~~No editing/deletion~~ — `edit_telegram_message` / `delete_telegram_message` tools implemented
- ~~Config knobs parsed but not applied~~ — `max_retries` and `timeout_seconds` flow end-to-end

## Non-Goals

**Out of scope for telegram_mcp:**
- Voice/video calls (Telegram client feature, not bot/user API)
- Payment processing (requires bot API, not user account)
- Admin operations (ban, promote, channel management)
- Replacing Telethon with another library (Telethon is mature, well-maintained, and already integrated)
- Telegram bot API support (architecture uses user account for seamless telegram-events integration)
- Real-time message streaming (telegram-events handles ingress; telegram_mcp is send-only)
- Custom UI or dashboard (MCP is tool-focused; UIs belong in agent frontends)

## Success Metrics

**Adoption:**
- 3+ agents using telegram_mcp in production (currently: secretary)
- 100+ messages sent per day without errors

**Reliability:**
- 99% send success rate (excluding user errors like invalid recipient)
- <5% retry rate for network/rate limit errors
- Zero unhandled exceptions in MCP server

**Developer Experience:**
- <10 min to add new recipient (with dynamic registry)
- <5 min to send first message (with current setup)
- Zero manifest changes needed for recipient updates (post-registry implementation)

**Performance:**
- <2s p95 latency for text messages
- <10s p95 latency for media messages (depends on file size)
- <1s MCP tool call overhead (JSON-RPC + stdio)

---

**Next Review:** Q3 2026
**Owner:** OrchestraThreads Core Team
**Feedback:** Open an issue or PR in the main repository.
