# ORCHESTRA MEMORY DOMAIN

## OVERVIEW
`orchestra_memory` = standalone local-memory service with HTTP lifecycle endpoints + MCP tool surface. Wraps local store, collection lifecycle, memory read/write ops behind compact runtime.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | logging setup + `run_service()` |
| Runtime wrapper | `service_runtime.py` | thin entry into app/lifecycle runner |
| Service lifecycle | `service_lifecycle.py` | `OrchestraMemoryService` |
| App/runner helpers | `service_app.py`, `service_runner.py`, `service_ops.py` | aiohttp build + lifecycle ops |
| Store composition root | `store.py` | `OrchestraMemoryStore` over read/write/lifecycle ops |
| Store internals | `store_*` | rows, validation, collection, lifecycle, writes, reads |
| MCP surface | `mcp/` | protocol, transport, server, tool specs |
| Client | `client.py` | HTTP client for memory service |
| Tests | `tests/` | service, MCP, slug scoping, secretary e2e, runtime smoke |

## CONVENTIONS
- Keep runtime thin. Most behavior belongs in store/service op modules.
- Preserve split between lifecycle, reads, writes in store layer.
- MCP + HTTP paths must reflect same memory semantics.

## ANTI-PATTERNS
- Do not let `service_runtime.py` become second impl layer.
- Do not bypass store validation/rules when adding new write paths.
- Do not treat memory tests as unit-only. Secretary e2e + runtime smoke coverage matter here.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_memory.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_memory_service.py`, `tests/test_memory_mcp_server.py`, `tests/test_memory_secretary_e2e.py`, `tests/test_secretary_runtime_smoke.py` are best first reads after behavior changes.
