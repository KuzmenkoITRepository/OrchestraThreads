# Orchestra Agents

`core.orchestra_agents` is a separate HTTP lifecycle service for manifest-defined agents.

Responsibilities:

- own local manifest registry
- validate and reload manifests
- start, stop, restart, and inspect agent containers through Docker
- enforce a standard HTTP runtime contract for connected agents

Main entry points:

- service: `python -m core.orchestra_agents.service_main`
- runtime contract: `core.orchestra_agents.runtime`
- scaffold helper: `python -m core.orchestra_agents.scaffold`

HTTP endpoints:

- `GET /healthz`
- `GET /api/v1/agents`
- `GET /api/v1/agents/{slug}`
- `GET /api/v1/agents/{slug}/status`
- `POST /api/v1/agents/{slug}/start`
- `POST /api/v1/agents/{slug}/stop`
- `POST /api/v1/agents/{slug}/restart`
- `GET /api/v1/manifests`
- `GET /api/v1/manifests/{slug}`
- `POST /api/v1/manifests/validate`
- `POST /api/v1/registry/reload`

Manifest shape:

- top-level: `slug`, `display_name`, `status`
- `agent`: `working_dir`, `http_endpoint`, `system_prompt_file`
- `runtime`: `driver`, `image`, `entrypoint`, `command`, `mounts`, `env`, `env_passthrough`
- `backend`: `type`, `config`

The service also accepts the earlier flat Orchestra-style fields and normalizes them into the new nested schema.

Template:

- bundled template root: `src/core/orchestra_agents/templates/agent`
- generic runtime image dockerfile: `Dockerfile.agent_runtime`
- `agent_mux` runtime image dockerfile: `Dockerfile.agent_mux_runtime`
- scaffold example:

```bash
PYTHONPATH=src python -m core.orchestra_agents.scaffold \
  --slug coding_agent \
  --output-dir agents/coding_agent \
  --backend-type codex_framework
```

Local runtime images:

- `orchestra-agent-runtime:latest` is the generic Python agent runtime image
- `orchestra-agent-mux-runtime:latest` is the codex-only `agent_mux` runtime image and includes `agent-mux` plus the `codex` CLI
- `DockerDriver` will auto-build these known local images on first `start` when they are missing from the local Docker daemon

Runtime context semantics:

- agent runtimes expose a durable agent-owned `context_id` in `GET /healthz` and `GET /last_status`
- `POST /clear_context` rotates `context_id` and increments `context_generation`
- `agent_mux` runtimes keep a compact durable context memory until `POST /clear_context`
- `agent_mux` is a generic event runtime; it is not thread-centric and does not own workflow semantics
- `thread_id`, `chat_id`, and other external routing identities may appear in event payloads, but they are opaque integration data for tools, not runtime identity
- concrete agents may attach `orchestra_threads` or other MCP servers through runtime config when they need those capabilities
