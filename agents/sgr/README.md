# SGR Minimax Example Agent

`agents/sgr` is a manifest-driven, event-driven example agent:

- lifecycle via `core.orchestra_agents`
- MCP tools loaded from manifest `backend.config.mcp_servers`
- LLM routing via `omniroute`

What it does:

- starts behind the standard HTTP runtime contract
- receives `/event` callbacks from the platform
- runs a proactive tool loop: event → LLM → MCP tool response
- calls LLM through the OmniRoute OpenAI-compatible route
- answers only through injected MCP tools, never by returning raw assistant text to `/event`

Default routing:

- `route_policy`: `codex_only`
- `model`: `cx/gpt-5.4-mini`

The defaults target the Codex/GPT OmniRoute family. Override them with env to switch to other OmniRoute models.

## Files

- `manifest.yaml`: lifecycle and runtime wiring for `orchestra_agents`
- `system_prompt.md`: prompt used for the Minimax call
- `agent_runtime/backend.py`: runtime/backend adapter
- `agent_runtime/main.py`: agent entrypoint

## Run

Start the platform services first:

```bash
docker compose up --build -d postgres orchestra-threads orchestra-agents orchestra-omniroute
```

Configure OmniRoute credentials in `.env` before starting the stack:

```bash
export OMNIROUTE_INITIAL_PASSWORD="CHANGEME"
export OMNIROUTE_API_KEY="<api-key>"
```

Provider-specific upstream credentials stay in the local project `.env` through `OPENAI_API_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`.

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
- `OMNIROUTE_URL`
- `OMNIROUTE_API_KEY`
- `SGR_MAX_REASONING_STEPS`
- `SGR_MAX_DIRECT_TEXT_RETRIES`
- `LOG_LEVEL`

## Notes

- The runtime is tool-only for outward actions: replies go through MCP tools configured in the manifest.
- It uses compact event context to keep prompt size down.
- `inactive` can wake the agent proactively when `react_to_inactive=true`.
- Delivery dedupe still happens per incoming event id inside the runtime.
