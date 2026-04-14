# ORCHESTRA AGENTS DOMAIN

## OVERVIEW
`orchestra_agents` owns manifest loading, validation, Docker lifecycle, scaffolding, migrations, shared HTTP runtime contract for managed agents. Backend adapters live under `backends/`. Templates + parity tests keep adapters aligned.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Lifecycle runtime | `service/runtime.py` | `OrchestraAgentsService` impl |
| Route split | `service_routes.py`, `_service_read_ops.py`, `_service_write_ops.py` | HTTP read/write behavior |
| State holder | `service_state.py` | registry + driver + lock |
| Service entry | `service_main.py` | process boot |
| Manifest parsing/building | `manifest.py`, `registry.py`, `_manifest_*` | normalization, schema handling, legacy-shape support |
| Migration flow | `_migration_*`, `backend_migration_support.py` | migration CLI/support logic |
| Docker lifecycle | `docker_driver/`, `_docker_*` | runtime resolution, support, specs |
| Shared runtime contract | `runtime/` | `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context` |
| Backend adapters | `backends/` | `sgr`, `agent_mux`, `opencode`, backend helpers |
| agent_mux refs | `backends/agent_mux/`, `templates/agent_mux/` | mux behavior + scaffold contract |
| Skills/templates | `skills/`, `templates/`, `scaffold.py` | scaffolded layouts, skill assets |
| Tests | `tests/` | runtime contract, Docker, registry, parity, templates |

## CONVENTIONS
- Keep agent lifecycle separate from thread ownership. Manifests describe runtime shape, not orchestration semantics.
- Preserve compatibility with legacy-flat manifest fields while parser/migration code still supports them.
- Health here = Docker/container state + HTTP probe behavior.
- Keep mux behavior anchored in `backends/agent_mux/` + `templates/agent_mux/`. Do not invent second shared runtime layer unless code really grows one.

## ANTI-PATTERNS
- Do not push `thread_id` semantics into generic runtime contract.
- Do not skip manifest validation or registry reload when changing manifest shape.
- Do not let templates drift from exported runtime behavior. Parity tests exist for that.
- Do not hide Docker/runtime resolution in prompts or manifests when it belongs in `docker_driver/` or backend code.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_agents.service_main
PYTHONPATH=src python -m core.orchestra_agents.scaffold --help
docker compose --profile test run --rm test
```

## NOTES
- `docs/` under this domain + `templates/agent_mux/IMPLEMENTATION_PLAN.md` are good boundary refs before mux changes.
- If change touches backends + templates together, run parity-oriented tests first.
