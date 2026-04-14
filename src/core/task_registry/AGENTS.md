# TASK REGISTRY DOMAIN

## OVERVIEW
`task_registry` is a standalone task service with HTTP endpoints and MCP task tools. It owns task persistence, checklist/comment mutations, and the task-facing store/API contract.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | logging setup + `run_service()` |
| HTTP runtime | `service_runtime.py` | `TaskRegistryService`, runtime loop |
| Web helpers | `service_runtime_web.py` | app setup, site start, shutdown |
| Store composition root | `store.py` | combines task/checklist/comment store mixins |
| Store internals | `store_base.py`, `store_tasks.py`, `store_checklists.py`, `store_comments.py`, `store_tasks_*` | persistence and typed task payloads |
| MCP surface | `mcp/` | server, tool specs, payloads, create/update tools |
| Schema | `schema.sql` | service schema source |
| Tests | `tests/` | integration coverage for service/store/tool behavior |

## CONVENTIONS
- Keep the task store composed by concern: tasks, checklists, comments.
- Prefer typed payload/helper modules over loose JSON dict plumbing.
- Changes to MCP task mutations should stay aligned with the HTTP/store contract.

## ANTI-PATTERNS
- Do not add task mutation logic directly to MCP handlers when it belongs in store/service modules.
- Do not bypass schema-aware store helpers with ad hoc SQL in unrelated files.
- Do not forget integration coverage; this domain currently leans heavily on it.

## COMMANDS
```bash
PYTHONPATH=src python -m core.task_registry.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_integration.py` is the main semantic regression test here.
