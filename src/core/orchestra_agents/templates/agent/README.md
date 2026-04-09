# __AGENT_DISPLAY_NAME__

This directory is the minimal Orchestra agent template.

What is fixed:

- manifest-driven lifecycle through `core.orchestra_agents`
- standard HTTP runtime contract:
  - `GET /healthz`
  - `POST /event`
  - `POST /stop`
  - `GET /last_status`
  - `POST /clear_context`
- backend adapter boundary behind `TemplateBackend`
- runtime entrypoint comes from `core.orchestra_agents.backends.example.main`

What you replace:

- `backend_type` in `manifest.yaml`
- optional prompt in `system_prompt.md`
- runtime `env` and mounts in `manifest.yaml`

The HTTP layer should stay stable even if the backend later becomes Codex, SGR, or Claude Code.
