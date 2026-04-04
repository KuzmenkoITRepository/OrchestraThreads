# Telegram MCP - Manual QA Guide

## Prerequisites

1. **Telegram API Credentials**: Same as telegram-events service uses
   - API ID and API Hash from https://my.telegram.org
   - Session string from telegram-events (same user account - Василий)
2. **Chat ID**: Your Telegram user ID (Ivan)

## Environment Setup

Use the same environment variables as telegram-events:

```bash
export TELEGRAM_API_ID="12345678"
export TELEGRAM_API_HASH="abcdef1234567890abcdef1234567890"
export TELEGRAM_SESSION_STRING="1BVtsOK4Bu..."  # Same as telegram-events
export TELEGRAM_CHAT_ID_IVAN="123456789"
```

## Test 1: Standalone MCP Server Test

Test the MCP server directly via stdio:

```bash
cd /home/odinykt/projects/OrchestraThreads
export TELEGRAM_API_ID="your_api_id"
export TELEGRAM_API_HASH="your_api_hash"
export TELEGRAM_SESSION_STRING="your_session_string"
export TELEGRAM_CHAT_ID_IVAN="your_chat_id"
export PYTHONPATH=src

# Test initialize
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 -m telegram_mcp

# Test tools/list
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python3 -m telegram_mcp

# Test send_telegram_message
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"send_telegram_message","arguments":{"message":"Test from telegram-mcp","recipient":"ivan"}}}' | python3 -m telegram_mcp
```

**Expected Results:**
- Initialize: Returns protocol version "2024-11-05" and server info
- Tools/list: Returns array with "send_telegram_message" tool
- Send message: Returns `{"ok": true, "message_id": <number>}` and you receive the message in Telegram from Василий's account

## Test 2: Docker Build Test

Build the Docker image with telegram_mcp included:

```bash
cd /home/odinykt/projects/OrchestraThreads
docker compose build orchestra-threads
```

**Expected Result:** Build succeeds without errors

## Test 3: Secretary Integration Test

Start the secretary agent with telegram-mcp:

```bash
cd /home/odinykt/projects/OrchestraThreads

# Ensure environment variables are set (same as telegram-events)
export TELEGRAM_API_ID="your_api_id"
export TELEGRAM_API_HASH="your_api_hash"
export TELEGRAM_SESSION_STRING="your_session_string"
export TELEGRAM_CHAT_ID_IVAN="your_chat_id"

# Start required services
docker compose up -d postgres orchestra-threads orchestra-agents llm-proxy

# Start secretary agent
docker compose --profile agents up -d secretary

# Check secretary logs
docker compose logs secretary -f
```

**Expected Results:**
- Secretary container starts successfully
- Logs show MCP server "telegram" spawned
- No errors about missing telegram_mcp module
- Telethon client connects successfully

## Test 4: End-to-End Message Send

Send a message to secretary asking it to send you a Telegram message:

```bash
# Using orchestra-threads API
curl -X POST http://localhost:8788/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent_slug": "test",
    "to_agent_slug": "secretary",
    "message_text": "Please send me a test message on Telegram using the send_telegram_message tool. My recipient alias is ivan."
  }'
```

**Expected Results:**
- Secretary receives the message
- Secretary uses send_telegram_message tool
- You receive a message in Telegram from Василий's account (not a bot)
- Secretary responds confirming the message was sent

## Test 5: Error Handling

Test error cases:

### Invalid recipient
```bash
echo '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"send_telegram_message","arguments":{"message":"Test","recipient":"unknown"}}}' | TELEGRAM_API_ID="123" TELEGRAM_API_HASH="abc" TELEGRAM_SESSION_STRING="" TELEGRAM_CHAT_ID_IVAN="123" PYTHONPATH=src python3 -m telegram_mcp
```

**Expected:** Returns `{"ok": false, "error": "Unknown recipient alias: unknown"}`

### Empty message
```bash
echo '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"send_telegram_message","arguments":{"message":"","recipient":"ivan"}}}' | TELEGRAM_API_ID="123" TELEGRAM_API_HASH="abc" TELEGRAM_SESSION_STRING="" TELEGRAM_CHAT_ID_IVAN="123" PYTHONPATH=src python3 -m telegram_mcp
```

**Expected:** Returns `{"ok": false, "error": "Message text is required"}`

### Invalid credentials
```bash
echo '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"send_telegram_message","arguments":{"message":"Test","recipient":"ivan"}}}' | TELEGRAM_API_ID="invalid" TELEGRAM_API_HASH="invalid" TELEGRAM_SESSION_STRING="" TELEGRAM_CHAT_ID_IVAN="123" PYTHONPATH=src python3 -m telegram_mcp
```

**Expected:** Server fails to connect with Telethon authentication error

## Verification Checklist

- [ ] MCP server responds to initialize request
- [ ] MCP server lists send_telegram_message tool
- [ ] Sending message via MCP returns success
- [ ] Message appears in Telegram from Василий's account
- [ ] Docker build includes telegram_mcp
- [ ] Secretary manifest includes telegram MCP server
- [ ] Secretary spawns telegram MCP server on startup
- [ ] Secretary can use send_telegram_message tool
- [ ] Error handling works for invalid inputs
- [ ] Logs show appropriate info/warning/error messages
- [ ] Uses same session as telegram-events (same user account)

## Troubleshooting

### Module not found: telegram_mcp
- Check PYTHONPATH includes `src` directory
- Verify directory is named `telegram_mcp` (underscore, not hyphen)

### telethon not found
- Install dependencies: `pip install -r requirements.txt`
- In Docker: ensure image is rebuilt after adding telegram_mcp

### Authentication failed
- Verify API_ID and API_HASH are correct (from https://my.telegram.org)
- Check session string is valid (same as telegram-events uses)
- Ensure session string matches the API_ID/API_HASH

### Message not received
- Verify chat ID is correct
- Check Telethon client connected successfully (check logs)
- Ensure user account (Василий) has permission to message the recipient
- Check Telegram API logs in MCP server output

### Secretary doesn't use the tool
- Verify MCP server is listed in secretary logs
- Check secretary's system prompt allows tool usage
- Ensure secretary has access to tool via MCP protocol
- Verify all environment variables are passed through manifest
