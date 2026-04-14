# ORCHESTRA THREAD DOMAIN

## OVERVIEW
`orchestra_thread` owns durable thread identity, message/notification delivery, retries, inactivity wakeups, UI/API read surfaces, thread-facing MCP tools. One of repo's heaviest domains. Most semantic changes land here.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Core runtime | `service/runtime.py` | `OrchestraThreadsService`, route wiring, delivery loops |
| Service package | `service/` | `main.py`, `flows/`, summary/snapshot helpers |
| HTTP handlers | `http_handlers.py` | read/write handler classes |
| Shared request payloads | `service_message_requests.py`, `service_notification_requests.py` | typed request shapes |
| Runtime config/shared helpers | `service_runtime_config.py`, `service_shared.py` | boot + shared responses |
| Store composition root | `store.py` | thin composition facade for store mixins |
| Store mixins | `store_*.py` | creation, events, query, delivery, notifications, agents, idempotency |
| MCP surface | `mcp/`, `mcp_thread_*.py`, `mcp_protocol*.py`, `mcp_transport.py` | tool specs, routing, context, views |
| CLI / local agent entry | `agent_cli/` | package entry via `agent_cli/__main__.py` |
| Docs | `docs/` | read before semantic changes |
| Tests | `tests/` | e2e, MCP, smoke, CLI, lifecycle coverage |

## CONVENTIONS
- `thread_id` = durable unit of work. Agent-local state must not replace it.
- Keep compact-first behavior: summaries, guide views, bounded context before raw replay.
- `service/runtime.py` = semantic hotspot. `service.py`-style facades should stay thin.
- Edit specific `store_*.py` module for store changes. `store.py` is composition only.
- Keep UI/API + MCP surfaces backed by same service state.

## ANTI-PATTERNS
- Do not move thread workflow semantics into CLI agents, edge relays, generic runtimes.
- Do not assume exact-once delivery. Callback model is retry-oriented.
- Do not change terminal-state or inactivity behavior without docs + tests together.
- Do not hunt in `mcp_handlers.py` for all MCP logic. Real logic is spread across `mcp_thread_*` + `mcp/` modules.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_thread.service.main
PYTHONPATH=src python -m core.orchestra_thread.agent_cli --help
docker compose --profile test run --rm test
```

## NOTES
- Navigation path now includes `service/flows/`, `thread_summary.py`, `thread_snapshot.py`.
- For delivery/status changes, start with `tests/test_e2e_mvp.py`, `tests/test_e2e_thread_flow.py`, `tests/test_mcp_server.py`.
