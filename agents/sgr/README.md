# SGR Minimax Example Agent

`agents/sgr` is a manifest-driven example agent for the new Orchestra split:

- lifecycle via `core.orchestra_agents`
- thread delivery via `core.orchestra_thread`
- LLM routing via `core.llm_proxy`

What it does:

- starts behind the standard HTTP runtime contract
- registers itself in `orchestra_thread` on startup
- keeps agent heartbeat alive
- receives `/event` callbacks from `orchestra_thread`
- fetches compact thread state instead of full history
- runs a proactive tool loop through the compact `orchestra-threads-mcp` surface
- calls Minimax through `llm_proxy` using the OpenAI-compatible route
- answers only through `thread_send` and `thread_status`, never by returning raw assistant text to `/event`

Default routing:

- `route_policy`: `minimax_only`
- `model`: `MiniMax-M2.7`

The defaults are safe placeholders. Override them with env when your Minimax upstream uses another model id.

## Files

- `manifest.yaml`: lifecycle and runtime wiring for `orchestra_agents`
- `system_prompt.md`: prompt used for the Minimax call
- `agent_runtime/backend.py`: runtime/backend adapter
- `agent_runtime/main.py`: agent entrypoint

## Run

Start the platform services first:

```bash
docker compose up --build -d postgres orchestra-threads orchestra-agents llm-proxy
```

If `llm-proxy` should forward Minimax traffic, set its fallback env before starting it:

```bash
export LLM_PROXY_FALLBACK_OPENAI_API_BASE_URL="https://<your-openai-compatible-endpoint>/v1"
export LLM_PROXY_FALLBACK_OPENAI_API_KEY="<api-key>"
export LLM_PROXY_FALLBACK_OPENAI_MODEL="MiniMax-M2.7"
```

In the current repo `llm-proxy` reads OpenAI-compatible Minimax creds from the local project `.env` through `OPENAI_API_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`.

Then reload manifests and start the agent:

```bash
curl -X POST http://127.0.0.1:8790/api/v1/registry/reload
curl -X POST http://127.0.0.1:8790/api/v1/agents/sgr/start
```

You can inspect runtime status here:

```bash
curl http://127.0.0.1:8790/api/v1/agents/sgr/status
curl http://127.0.0.1:8788/agents
```

## Override knobs

`manifest.yaml` already sets working defaults, but these env vars can be passed through from the host:

- `LLM_CLIENT_MODEL`
- `LLM_CLIENT_ROUTE_POLICY`
- `LLM_CLIENT_TIMEOUT_SECONDS`
- `LLM_CLIENT_TEMPERATURE`
- `LLM_CLIENT_MAX_TOKENS`
- `ORCHESTRA_THREADS_URL`
- `LLM_PROXY_URL`
- `LLM_PROXY_ENABLED`
- `SGR_HEARTBEAT_INTERVAL_SECONDS`
- `SGR_MAX_REASONING_STEPS`
- `SGR_MAX_DIRECT_TEXT_RETRIES`
- `LOG_LEVEL`

## Notes

- The runtime is tool-only for outward actions: replies and lifecycle updates go through OrchestraThreads MCP tools.
- It uses `thread_compact` plus the compact service guide to keep prompt size down.
- `inactive` can wake the agent proactively when `react_to_inactive=true`.
- Delivery dedupe still happens per incoming event id inside the runtime.
