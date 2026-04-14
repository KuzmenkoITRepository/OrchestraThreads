# SCHEDULER CRON DOMAIN

## OVERVIEW
`scheduler_cron` is a standalone scheduling service. It owns scheduled job persistence, runtime bootstrapping, scheduler-engine coordination, executor dispatch, and health exposure.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | logging setup + dynamic runtime import |
| HTTP runtime | `service_runtime.py` | `SchedulerCronService`, `/healthz`, start/stop flow |
| Runtime helpers | `service_runtime_support.py` | started runtime, start/stop helpers, constants |
| Bootstrap | `bootstrap.py`, `bootstrap_ops.py`, `bootstrap_data.py` | initial job loading |
| Executor | `executor/`, `executor_runtime.py`, `executor_helpers.py` | job execution support |
| Scheduler engine | `scheduler_engine/`, `scheduler_engine_*` | scheduling logic and types |
| Store composition root | `store.py` | dynamic composition over base/jobs/runs stores |
| Store internals | `store_base.py`, `store_jobs*.py`, `store_runs*.py` | job/run persistence |
| Schema | `schema.sql` | scheduler DB schema |
| Tests | `tests/` | bootstrap, engine, executor, store, service integration, e2e acceptance |

## CONVENTIONS
- Keep scheduler engine, executor, and persistence concerns separate.
- `store.py` is a dynamic composition facade; edit the underlying store modules instead.
- Runtime start/stop and bootstrap ordering matter; preserve that sequence when refactoring.

## ANTI-PATTERNS
- Do not move scheduling logic into HTTP handlers.
- Do not inline executor or engine boot code where helper modules already split it cleanly.
- Do not remove the justified dynamic-composition explanation from `store.py` unless you also remove that pattern.

## COMMANDS
```bash
PYTHONPATH=src python -m core.scheduler_cron.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_service_integration.py` and `tests/test_e2e_acceptance.py` are the fastest behavior checks after runtime changes.
