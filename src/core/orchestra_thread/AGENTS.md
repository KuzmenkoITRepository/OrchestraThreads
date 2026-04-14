# ORCHESTRA THREAD DOMAIN

## OVERVIEW
`orchestra_thread` owns durable thread identity, message/notification delivery, retries, inactivity wakeups, UI/API read surfaces, and thread-facing MCP tools. This is still one of the repo’s heaviest domains; most semantic changes end up here.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Core runtime | `service/runtime.py` | `OrchestraThreadsService`, route wiring, delivery loops |
| Service package | `service/` | `main.py`, `flows/`, summary/snapshot helpers |
| HTTP handlers | `http_handlers.py` | read/write handler classes |
| Shared request payloads | `service_message_requests.py`, `service_notification_requests.py` | typed request shapes |
| Runtime config/shared helpers | `service_runtime_config.py`, `service_shared.py` | service boot and shared responses |
| Store composition root | `store.py` | thin composition facade for store mixins |
| Store mixins | `store_*.py` | creation, events, query, delivery, notifications, agents, idempotency, clock |
| MCP surface | `mcp/`, `mcp_thread_*.py`, `mcp_protocol*.py`, `mcp_transport.py` | thread tool specs, routing, context, views |
| CLI / local agent entry | `agent_cli/` | package now, not a single file |
| Docs | `docs/` | read before changing semantics |
| Tests | `tests/` | e2e, MCP, smoke, CLI, lifecycle coverage |

## CONVENTIONS
- `thread_id` is the durable unit of work. Agent-local state must not replace it.
- Keep compact-first behavior: summaries, guide views, and bounded context before raw replay.
- `service/runtime.py` is the semantic hotspot; `service.py`-style facades should stay thin.
- Edit the specific `store_*.py` module for store changes; `store.py` is composition only.
- Keep UI/API and MCP surfaces backed by the same underlying service state.

## ANTI-PATTERNS
- Do not move thread workflow semantics into CLI agents, edge relays, or generic runtimes.
- Do not assume exact-once delivery; the callback model is retry-oriented.
- Do not change terminal-state or inactivity behavior without updating docs and tests together.
- Do not treat `mcp_handlers.py` as the real MCP center; the logic is spread across the `mcp_thread_*` and `mcp/` modules.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_thread.service.main
PYTHONPATH=src python -m core.orchestra_thread.agent_cli --help
docker compose --profile test run --rm test
```

## NOTES
- The service package has grown: `service/flows/`, `thread_summary.py`, and `thread_snapshot.py` are now part of the navigation path.
- If you are changing delivery or status semantics, start with `tests/test_e2e_mvp.py`, thread-flow tests, and MCP server tests.
