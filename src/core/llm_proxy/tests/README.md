# LLM Proxy Tests

## Unit Tests

Standard unit tests with mocked upstreams and fake telemetry.

Run via Docker:

```bash
docker compose --profile test run --rm test
```

These tests always run and verify:
- Account rotation logic
- Fallback behavior
- Langfuse grouping logic (with fake telemetry)
- Request routing
- Error handling

## E2E Tests with Real Backends

E2E tests against the real MiniMax path and a live Langfuse instance.

**These tests are disabled by default** and only run when explicitly enabled.

### Prerequisites

1. Running llm-proxy service with real backend configuration
2. Running Langfuse instance with API access
3. Valid Langfuse API keys

### Setup

Start the full stack:

```bash
docker compose up -d
```

Configure Langfuse in `.env`:

```bash
LLM_PROXY_LANGFUSE_ENABLED=1
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://langfuse:3000
```

Restart llm-proxy:

```bash
docker compose restart llm-proxy
```

### Running E2E Tests

From host:

```bash
export E2E_REAL_BACKENDS_ENABLED=1
export LLM_PROXY_BASE_URL=http://localhost:8791
export LANGFUSE_BASE_URL=http://localhost:3000
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...

python -m unittest src.core.llm_proxy.tests.test_e2e_real_backends -v
```

Inside the Docker test environment:

```bash
docker compose build test
docker compose --profile test run --rm -e E2E_REAL_BACKENDS_ENABLED=1 test \
  python -m unittest discover -s src/core/llm_proxy/tests -p "test_e2e_real_backends.py" -v
```

### What E2E Tests Verify

1. **Readable MiniMax Dialogue in Langfuse**
   - Real chat-completions requests through `/minimax/v1/chat/completions`
   - Unique run markers so each test run is easy to find in the Langfuse UI
   - Multi-turn request content is present in Langfuse trace input and generation input/output
   - Returned assistant response preserves requested memory from the dialogue

2. **Operational Metadata for Real Runs**
   - Generation metadata records `selected_transport=fallback`
   - Generation metadata includes latency
   - Generation usage and model parameters are captured for the real MiniMax execution

3. **Session Grouping**
   - Multiple requests with same context_id grouped under the same session_id
   - Distinct follow-up requests remain individually visible inside the same grouped session
   - Session ID format: `agent_slug:context_id`

4. **Context Rotation**
   - Changing context_id creates a new Langfuse session
   - Session IDs are properly isolated
   - Each rotated session contains only its own unique dialogue marker

### Troubleshooting

**Tests are skipped:**
- Ensure `E2E_REAL_BACKENDS_ENABLED=1` is set
- Check that Langfuse keys are configured

**No traces found in Langfuse:**
- Verify `LLM_PROXY_LANGFUSE_ENABLED=1` in llm-proxy config
- Check llm-proxy logs for Langfuse connection errors
- Ensure Langfuse is healthy: `docker compose ps langfuse`

**Trace format validation fails:**
- Check Langfuse API version compatibility
- Verify the new run marker appears in both the trace input and generation output in Langfuse UI

**Connection errors:**
- Verify services are running: `docker compose ps`
- Check network connectivity between containers
- Ensure ports are not blocked by firewall
