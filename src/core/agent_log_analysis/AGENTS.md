# AGENT LOG ANALYSIS DOMAIN

## OVERVIEW
`agent_log_analysis` is a standalone service for ingesting agent logs, storing raw records, building aggregates/correlations, and serving both HTTP and MCP query surfaces.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | logging setup + `run_service()` |
| HTTP runtime | `service_runtime.py` | `AgentLogAnalysisService`, `build_app()`, `run_service()` |
| Runtime decomposition | `service_runtime_parts/` | dependencies, operations, web boot helpers |
| State holder | `service_state.py` | config + started/store state |
| Store composition root | `store.py` | composes ingest/raw-log/query/aggregate/correlation mixins |
| Store mixins | `store_*.py` | DB reads/writes split by responsibility |
| Ingest/query logic | `ingest_service*.py`, `event_query_service*.py`, `timeline_service.py`, `aggregation_service.py`, `correlation_service.py` | service-layer behavior |
| Validation layer | `validation_*` | payload/query normalization and bounds enforcement |
| MCP surface | `mcp/` | protocol, transport, server, tools |
| Tests | `tests/` | store, service, MCP, aggregation, timeline, validation coverage |

## CONVENTIONS
- Keep ingest, query, and correlation concerns separate; this domain already decomposes aggressively for WPS/mypy reasons.
- Edit the targeted `validation_*` or `store_*` module instead of re-inflating `service_runtime.py`.
- Treat `store.py` as composition root only.
- HTTP and MCP should reuse the same underlying service/store semantics.

## ANTI-PATTERNS
- Do not collapse validation stages back into giant request handlers.
- Do not hide SQL/query-shaping logic inside HTTP handlers.
- Do not bypass the composed store mixins by adding duplicate persistence code in service modules.

## COMMANDS
```bash
PYTHONPATH=src python -m core.agent_log_analysis.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_service_integration.py` and `tests/test_mcp_server.py` are the fastest semantic checks after runtime-surface changes.
- The directory is intentionally granular; that granularity is part of the design, not clutter to undo.
