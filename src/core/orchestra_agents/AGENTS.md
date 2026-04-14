# ORCHESTRA AGENTS DOMAIN

## OVERVIEW
`orchestra_agents` owns manifest loading, validation, Docker lifecycle control, scaffolding, migrations, and the shared HTTP runtime contract for managed agents. Backend adapters live under `backends/`; templates and parity tests keep those adapters aligned.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Lifecycle runtime | `service/runtime.py` | `OrchestraAgentsService` implementation |
| Route split | `service_routes.py`, `_service_read_ops.py`, `_service_write_ops.py` | HTTP read/write behavior |
| State holder | `service_state.py` | registry + driver + lock |
| Service entry | `service_main.py` | process boot |
| Manifest parsing/building | `manifest.py`, `registry.py`, `_manifest_*` | normalization and schema handling |
| Migration flow | `_migration_*`, `backend_migration_support.py` | migration CLI/support logic |
| Docker lifecycle | `docker_driver/`, `_docker_*` | runtime resolution, support, specs |
| Shared runtime contract | `runtime/` | `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context` |
| Backend adapters | `backends/` | `sgr`, `agent_mux`, `opencode`, plus backend-specific helpers |
| agent_mux implementation references | `backends/agent_mux/`, `templates/agent_mux/` | current mux adapter behavior and scaffold contract |
| Skills/templates | `skills/`, `templates/`, `scaffold.py` | scaffolded agent layouts and skill assets |
| Tests | `tests/` | runtime contract, Docker, registry, parity, templates |

## CONVENTIONS
- Keep agent lifecycle separate from thread ownership. Manifests describe runtime shape, not orchestration semantics.
- Preserve compatibility between nested manifest shape and legacy-flat fields where the service still supports both.
- Health is two-part here: Docker/container state plus HTTP probe behavior.
- Keep mux behavior anchored in `backends/agent_mux/` and `templates/agent_mux/`; do not invent a second shared runtime layer unless the codebase actually grows one.

## ANTI-PATTERNS
- Do not push `thread_id` semantics into the generic runtime contract.
- Do not skip manifest validation or registry reload paths when changing manifest shape.
- Do not let templates drift from the exported runtime behavior; parity tests exist to catch that.
- Do not hide Docker/runtime resolution in prompts or manifests when it belongs in `docker_driver/` or backend code.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_agents.service_main
PYTHONPATH=src python -m core.orchestra_agents.scaffold --help
docker compose --profile test run --rm test
```

## NOTES
- `docs/` under this domain and `templates/agent_mux/IMPLEMENTATION_PLAN.md` are strong boundary references before changing mux behavior.
- If a change touches backends and templates together, run parity-oriented tests first.
