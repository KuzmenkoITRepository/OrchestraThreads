# TASK REGISTRY DOMAIN

## OVERVIEW
`task_registry` = standalone task service with HTTP health runtime + MCP task tools. Owns task persistence, checklist/comment mutations, task-facing store/API contract.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | logging setup + `run_service()` |
| HTTP runtime | `service_runtime.py` | `TaskRegistryService`, health runtime loop |
| Web helpers | `service_runtime_web.py` | app setup, `/healthz`, site start, shutdown |
| Store composition root | `store.py` | combine task/checklist/comment store mixins |
| Store internals | `store_base.py`, `store_tasks.py`, `store_checklists.py`, `store_comments.py`, `store_tasks_*` | persistence + typed task payloads |
| MCP surface | `mcp/` | server, tool specs, payloads, create/update tools |
| Schema | `schema.sql` | service schema source |
| Tests | `tests/` | integration coverage for service/store/tool behavior |

## CONVENTIONS
- Keep task store composed by concern: tasks, checklists, comments.
- Prefer typed payload/helper modules over loose JSON dict plumbing.
- Keep task semantics centered in store + MCP layers. HTTP runtime here is health-only.

## ANTI-PATTERNS
- Do not add task mutation logic directly to MCP handlers when it belongs in store/service modules.
- Do not hunt for CRUD HTTP routes in `service_runtime_web.py`. It exposes `/healthz`, not task mutation surface.
- Do not bypass schema-aware store helpers with ad hoc SQL in unrelated files.
- Do not skip integration coverage. Domain leans on it heavily.

## COMMANDS
```bash
PYTHONPATH=src python -m core.task_registry.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_integration.py` = main semantic regression test here.
