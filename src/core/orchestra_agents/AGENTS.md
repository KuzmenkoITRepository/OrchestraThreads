# ORCHESTRA AGENTS DOMAIN

## OVERVIEW
`orchestra_agents` owns manifest loading, validation, Docker lifecycle control, scaffolding, and the standard HTTP runtime contract shared by managed agents.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Lifecycle API | `service.py` | `/api/v1/agents/*`, `/api/v1/manifests/*`, `/api/v1/registry/reload` |
| Process boot | `service_main.py` | binds the lifecycle service |
| Manifest parsing | `manifest.py`, `registry.py` | nested + legacy-flat manifest normalization |
| Docker execution | `docker_driver.py` | build/start/health probing logic |
| Shared runtime contract | `runtime/app.py`, `runtime/backend.py`, `runtime/contracts.py` | `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context` |
| Agent scaffolding | `scaffold.py`, `templates/` | bundled agent and agent_mux templates |
| Tests | `tests/` | registry, runtime, scaffold, Docker, example-agent coverage |

## CONVENTIONS
- Keep agent lifecycle separate from thread semantics; manifests describe runtimes, not orchestration ownership.
- Preserve compatibility with both nested manifest shape and earlier flat Orchestra-style fields.
- Runtime templates are examples and contract carriers; keep the contract stable when adding new backend types.
- Health status is part Docker state, part HTTP probing; both matter.

## ANTI-PATTERNS
- Do not push `thread_id` or workflow ownership into the generic runtime contract.
- Do not break the minimal template when adding `agent_mux` or other backends; prefer additive changes.
- Do not make `/event` handlers block on long worker runs in managed runtimes.
- Do not skip manifest validation or registry reload paths when changing agent shape.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_agents.service_main
PYTHONPATH=src python -m core.orchestra_agents.scaffold --slug coding_agent --output-dir agents/coding_agent --backend-type codex_framework
docker compose --profile test run --rm test
```

## NOTES
- `templates/agent_mux/IMPLEMENTATION_PLAN.md` contains the strongest constraints for queue-first mux runtimes.
- `tests/test_runtime_contract.py`, `tests/test_docker_driver.py`, and `tests/test_agent_mux_template.py` cover most breaking surfaces.
