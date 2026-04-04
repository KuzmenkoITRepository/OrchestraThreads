# ORCHESTRA THREAD DOMAIN

## OVERVIEW
`orchestra_thread` owns durable thread identity, delivery, retries, inactivity wakeups, MCP-facing thread tools, and the read-only UI/API surface.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| HTTP surface | `service.py` | routes include `/agents/*`, `/api/v1/messages`, `/api/v1/notifications`, `/api/v1/threads/*`, `/api/v1/instructions` |
| Process boot | `service_main.py` | starts DB-backed service + aiohttp app |
| Persistence | `store.py` | Postgres-backed thread/event storage; large hotspot |
| MCP tool bridge | `mcp_server.py` | compact thread operations exposed to runtimes |
| Human/manual agent interface | `agent_cli.py` | `/event`, `/stop`, `/healthz` CLI agent surface |
| Architecture docs | `docs/README.md`, `docs/ARCH-DRAFT.md`, `docs/MCP-INTEGRATION-DRAFT.md` | read before changing semantics |
| Tests | `tests/` | e2e, CLI, MCP, smoke coverage |

## CONVENTIONS
- `thread_id` is the durable work identity; local runtime state must not replace it.
- Compact-first is the norm: prefer thread summaries/guides before expanding history.
- Status ownership matters: root service enforces message/notification flow and inactivity behavior.
- Keep the UI and API backed by the same underlying service state instead of forking logic.

## ANTI-PATTERNS
- Do not move workflow semantics into CLI agents, MCP clients, or agent runtimes.
- Do not assume exact-once delivery; callback delivery is retry-oriented.
- Do not add prompt-history replay where compact thread state is sufficient.
- Do not change thread terminal-state behavior without updating docs and tests together.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_thread.service_main
PYTHONPATH=src python -m core.orchestra_thread.agent_cli --slug human --target orchestra
docker compose --profile test run --rm test
```

## NOTES
- The heaviest files here are `service.py`, `store.py`, `mcp_server.py`, and `agent_cli.py`.
- `tests/test_e2e_mvp.py` and `tests/test_mcp_server.py` are the fastest way to confirm semantic changes.
