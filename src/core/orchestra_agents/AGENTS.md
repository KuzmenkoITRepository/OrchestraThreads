# ORCHESTRA AGENTS DOMAIN

## OVERVIEW
`orchestra_agents` owns manifest loading, validation, Docker lifecycle control, scaffolding, and the standard HTTP runtime contract shared by managed agents. Includes the `agent_mux_runtime/` subsystem (29 files) for multiplexed agent backends.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Lifecycle API | `service.py` | `OrchestraAgentsService` delegates to `service_routes.py` + `service_state.py` |
| HTTP routes | `service_routes.py` | `_AgentReadRoutes`, `_AgentWriteRoutes` with `_Guarded` error handling |
| Service state | `service_state.py` | `ServiceState` dataclass: registry + driver + lock |
| Process boot | `service_main.py` | binds the lifecycle service |
| Manifest parsing | `manifest.py`, `_manifest_parsing.py`, `registry.py` | nested + legacy-flat normalization |
| Errors | `errors.py` | `ManifestValidationError`, `ServiceError` |
| Docker execution | `docker_driver.py` | build/start/health probing logic |
| Shared runtime contract | `runtime/app.py`, `runtime/backend.py`, `runtime/contracts.py` | `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context` |
| Agent scaffolding | `scaffold.py`, `templates/` | bundled agent and agent_mux templates |
| Agent mux runtime | `agent_mux_runtime/` | 29-file subsystem: queue, dispatch, state, codex config, bootstrap |
| Mux entry point | `agent_mux_runtime/bootstrap.py` | `run_backend()`, `serve_backend()`, logging, manifest loading |
| Mux dispatch | `agent_mux_runtime/dispatch_engine.py` | `AgentMuxDispatchSpec`, payload marshaling |
| Mux state | `agent_mux_runtime/state_store.py` | `AgentMuxRuntimeState`, queue/context/dispatch coordination |
| Mux process | `agent_mux_runtime/backend_process.py` | spawns agent-mux binary, stdin payload |
| Mux queue | `agent_mux_runtime/queue_store.py`, `queue_mutations.py` | filesystem-backed queue with processing/failed dirs |
| Tests | `tests/` | registry, runtime, scaffold, Docker, example-agent, mux parity coverage |

## CONVENTIONS
- Keep agent lifecycle separate from thread semantics; manifests describe runtimes, not orchestration ownership.
- Preserve compatibility with both nested manifest shape and earlier flat Orchestra-style fields.
- Runtime templates are examples and contract carriers; keep the contract stable when adding new backend types.
- Health status is part Docker state, part HTTP probing; both matter.
- `agent_mux_runtime/` is the shared core; templates provide concrete backend blueprints and parity tests enforce alignment.

## ANTI-PATTERNS
- Do not push `thread_id` or workflow ownership into the generic runtime contract.
- Do not break the minimal template when adding `agent_mux` or other backends; prefer additive changes.
- Do not make `/event` handlers block on long worker runs in managed runtimes.
- Do not skip manifest validation or registry reload paths when changing agent shape.
- Do not diverge `agent_mux_runtime/` public API from what templates export — parity tests catch this.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_agents.service_main
PYTHONPATH=src python -m core.orchestra_agents.scaffold --slug coding_agent --output-dir agents/coding_agent --backend-type codex_framework
docker compose --profile test run --rm test
```

## NOTES
- `templates/agent_mux/IMPLEMENTATION_PLAN.md` contains the strongest constraints for queue-first mux runtimes.
- `tests/test_runtime_contract.py`, `tests/test_docker_driver.py`, `tests/test_agent_mux_template.py`, and `tests/test_agent_mux_runtime_parity.py` cover most breaking surfaces.
- Service is decomposed: `service.py` -> `service_routes.py` (HTTP) + `service_state.py` (state) + `errors.py` (error types).
