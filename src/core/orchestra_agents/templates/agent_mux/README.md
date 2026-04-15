# __AGENT_DISPLAY_NAME__

This directory is the `agent_mux` Orchestra agent template.

What is fixed:

- manifest-driven lifecycle through `core.orchestra_agents`
- standard HTTP runtime contract:
  - `GET /healthz`
  - `POST /event`
  - `POST /stop`
  - `GET /last_status`
  - `POST /clear_context`
- generic agent-side wrapper around `agent-mux`
- local durable runtime state under `runtime_state/`
- placeholder config roots for `.agent-mux` and `.codex`
- dedicated runtime image `orchestra-agent-mux-runtime:latest` with `agent-mux` and `codex`

What the scaffolded wrapper already does:

- accepts event deliveries quickly;
- persists incoming work into a local queue;
- deduplicates `event_id` values after durable enqueue;
- keeps a durable agent-owned `context_id` across requests and restarts;
- rotates `context_id` only on `POST /clear_context`;
- carries a compact durable context memory until explicit `clear_context`;
- exposes queue-oriented runtime status;
- generates runtime Codex config pointed at direct `omniroute`;
- writes generic active event context for optional MCP tools;
- launches `agent-mux --stdin` for codex-only worker execution.
- supports optional MCP server configuration from backend config;
- does not depend on `thread_id` or `chat_id` for runtime identity.

What you implement next:

- actual `agent-mux` dispatch execution;
- event-specific prompts and tool surfaces for each concrete agent;
- optional integrations such as `orchestra_threads`, Telegram ingress, or future services;
- steering, recovery, and direct Omniroute validation.

The execution layer is intended to live inside the agent runtime, so
external systems keep ownership of workflow semantics while `agent-mux`
stays an execution substrate.
