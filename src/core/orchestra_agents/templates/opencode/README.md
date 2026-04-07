# __AGENT_DISPLAY_NAME__

This directory is the `opencode` Orchestra agent template.

What is fixed:

- manifest-driven lifecycle through `core.orchestra_agents`
- standard HTTP runtime contract:
  - `GET /healthz`
  - `POST /event`
  - `POST /stop`
  - `GET /last_status`
  - `POST /clear_context`
- generic agent-side wrapper around `opencode serve`
- local durable runtime state under `runtime_state/`
- dedicated runtime image `orchestra-opencode-runtime:latest`

What the scaffolded wrapper already does:

- accepts event deliveries quickly;
- deduplicates `event_id` values before dispatch;
- keeps a durable agent-owned `context_id` across requests and restarts;
- maps the active `context_id` to an opencode session persisted in `session_map.json`;
- rotates `context_id` only on `POST /clear_context`;
- writes active event context for OrchestraThreads MCP tools;
- launches `opencode serve` locally and sends event prompts through its HTTP API;
- relies on OrchestraThreads MCP tools for all peer-facing output.

What you implement next:

- concrete system prompts and model choices for each agent;
- optional routing or specialization behavior;
- environment-specific omniroute credentials.
