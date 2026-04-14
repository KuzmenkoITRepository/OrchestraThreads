# ORCHESTRA MEMORY DOMAIN

## OVERVIEW
`orchestra_memory` is a standalone local-memory service with HTTP lifecycle endpoints and an MCP tool surface. It wraps a local store, collection lifecycle, and memory retrieval/write operations behind a compact runtime.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | logging setup + `run_service()` |
| Runtime wrapper | `service_runtime.py` | thin entry into app/lifecycle runner |
| Service lifecycle | `service_lifecycle.py` | `OrchestraMemoryService` |
| App/runner helpers | `service_app.py`, `service_runner.py`, `service_ops.py` | aiohttp build and lifecycle operations |
| Store composition root | `store.py` | `OrchestraMemoryStore` over read/write/lifecycle ops |
| Store internals | `store_*` | rows, validation, collection, lifecycle, writes, reads |
| MCP surface | `mcp/` | protocol, transport, server, tool specs |
| Client | `client.py` | HTTP client for the memory service |
| Tests | `tests/` | service, MCP, slug scoping, secretary e2e, runtime smoke |

## CONVENTIONS
- Keep the runtime thin; most behavior belongs in store/service operation modules.
- Preserve the split between lifecycle, reads, and writes in the store layer.
- MCP and HTTP paths must reflect the same memory semantics.

## ANTI-PATTERNS
- Do not let `service_runtime.py` become a second implementation layer.
- Do not bypass store validation/rules when adding new write paths.
- Do not treat memory tests as unit-only; secretary/runtime smoke coverage matters here.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_memory.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_memory_service.py`, `tests/test_memory_mcp_server.py`, and the secretary/runtime smoke tests are the best first reads after behavior changes.
