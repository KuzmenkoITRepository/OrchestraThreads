# LLM Proxy

`core.llm_proxy` is a separate HTTP routing service for Codex and OpenAI-compatible backends.

Responsibilities:

- own Codex account rotation state
- route requests across multiple Codex OAuth profiles
- fall back to an OpenAI-compatible provider when Codex accounts are unavailable
- expose a stable OpenAI-style and Codex-style HTTP contract for connected runtimes
- emit Langfuse traces for LLM activity inside the proxy

Main entry points:

- service: `python -m core.llm_proxy.service_main`
- router: `core.llm_proxy.router`
- client helpers: `core.llm_proxy.client_config`

HTTP endpoints:

- `GET /healthz`
- `GET /accounts/status`
- `GET /v1/models`
- `GET /codex/v1/models`
- `GET /minimax/v1/models`
- `POST /v1/chat/completions`
- `POST /codex/v1/chat/completions`
- `POST /minimax/v1/chat/completions`
- `POST /v1/responses`
- `POST /codex/v1/responses`
- `POST /minimax/v1/responses`
- `POST /v1/codex/responses`
- `POST /codex/v1/codex/responses`
- `POST /minimax/v1/codex/responses`

Routing modes:

- `managed_auto`: rotate Codex accounts, then fall back to OpenAI-compatible upstream
- `codex_only`: only Codex accounts
- `minimax_only`: direct OpenAI-compatible route without trying Codex accounts first

Important env vars:

- `LLM_PROXY_CODEX_UPSTREAM_BASE_URL`
- `LLM_PROXY_AUTH_PROFILES_PATH`
- `LLM_PROXY_CODEX_PRIMARY_PROFILE_ID`
- `LLM_PROXY_CODEX_PROFILE_IDS`
- `LLM_PROXY_ACCOUNT_FAILURE_COOLDOWN_SECONDS`
- `LLM_PROXY_STATE_PATH`
- `LLM_PROXY_FALLBACK_OPENAI_API_BASE_URL`
- `LLM_PROXY_FALLBACK_OPENAI_API_KEY`
- `LLM_PROXY_FALLBACK_OPENAI_MODEL`
- `LLM_PROXY_LANGFUSE_ENABLED`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_BASE_URL`

Langfuse grouping:

- `llm_proxy` groups traces by the stable agent context, not by `thread_id`
- grouping key is derived from `agent_slug + context_id`
- this pair is projected into Langfuse `session_id` so repeated requests within the same agent context appear together over time

## Local Langfuse Stack

Langfuse starts automatically with the main stack. Access the UI at `http://localhost:3000` (default port, configurable via `LANGFUSE_PORT`).

On first launch, create a project and generate API keys from the Langfuse UI.

Configure `llm-proxy` to use local Langfuse:

```bash
# In .env
LLM_PROXY_LANGFUSE_ENABLED=1
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://langfuse:3000
LLM_PROXY_LANGFUSE_ENVIRONMENT=local
LLM_PROXY_LANGFUSE_RELEASE=dev
```

Restart `llm-proxy`:

```bash
docker compose restart llm-proxy
```

Traces will appear in the Langfuse UI grouped by `agent_slug:context_id`.

To reset Langfuse data, remove the volume:

```bash
docker compose down -v
```
