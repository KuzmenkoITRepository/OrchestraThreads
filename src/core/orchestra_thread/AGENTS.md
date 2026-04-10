# ORCHESTRA THREAD DOMAIN

## OVERVIEW
`orchestra_thread` owns durable thread identity, delivery, retries, inactivity wakeups, MCP-facing thread tools, and the read-only UI/API surface. After refactoring: `service.py` is a thin re-export facade; all logic lives in `service/runtime.py` (1724 lines). Store is decomposed into 7 mixin modules. MCP is decomposed into 12+ `mcp_thread_*` files.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Core service logic | `service/runtime.py` | 1724-line hotspot: OrchestraThreadsService class, message/notification flows, delivery/inactivity loops |
| Facade re-export | `service.py` | thin re-export of `service.runtime.OrchestraThreadsService` and `build_app` |
| HTTP handlers | `http_handlers.py` | `HttpReadHandlers` + `HttpWriteHandlers` classes |
| Shared HTTP helpers | `service_shared.py` | `json_error`, `json_success`, `service_error_response`, `STATIC_DIR` |
| Common types/constants | `common.py` | `ServiceError`, thread status constants, `utc_now_iso`, text normalization |
| Process boot | `service/main.py` | starts DB-backed service + aiohttp app |
| Store facade | `store.py` | mixin composition of 7 store modules into `ThreadStore` |
| Store base | `store_base.py` | DB pool, schema handling, row serialization, `quote_ident` |
| Store: thread creation | `store_thread_creation.py` | `RootThreadRequest`, `ChildThreadRequest` |
| Store: events | `store_thread_events.py` | `AppendEventRequest`, event append logic |
| Store: queries | `store_thread_query.py` | thread/event fetching |
| Store: delivery | `store_delivery.py` | pending event delivery tracking |
| Store: notifications | `store_notifications.py` | notification state persistence |
| Store: agents | `store_agents.py` | agent registry integration |
| Store: idempotency | `store_idempotency.py` | idempotency key management |
| MCP server | `mcp_server.py` | `OrchestraThreadsMCPServer` — compact JSON-RPC 2.0 over stdio |
| MCP transport | `mcp_transport.py` | stdio framing for MCP |
| MCP protocol | `mcp_protocol.py` | protocol definitions |
| MCP routing | `mcp_thread_routing.py`, `mcp_thread_routing_modes.py` | send mode resolution (auto/root/child/exact) |
| MCP send tools | `mcp_thread_send_tools.py` | message/notification send tools |
| MCP status tools | `mcp_thread_status_tools.py` | thread status query tools |
| MCP view tools | `mcp_thread_view_*.py` | current, expand, guide, tools views |
| MCP context | `mcp_thread_context.py`, `mcp_tools_context.py` | thread/agent context for MCP tools |
| MCP common | `mcp_tools_common.py`, `mcp_thread_tool_specs.py` | shared tool utilities and specs |
| Active context | `active_context.py` | runtime active-context tracking |
| Thread client | `client.py` | HTTP client for thread service |
| Guide management | `guide.py` | guide/prompt loading |
| CLI agent | `agent_cli.py` | `/event`, `/stop`, `/healthz` CLI agent surface |
| Architecture docs | `docs/README.md`, `docs/ARCH-DRAFT.md`, `docs/MCP-INTEGRATION-DRAFT.md` | read before changing semantics |
| Tests | `tests/` | e2e (mvp, lifecycle, thread_flow, ui), CLI, MCP, smoke coverage |

## CONVENTIONS
- `thread_id` is the durable work identity; local runtime state must not replace it.
- Compact-first is the norm: prefer thread summaries/guides before expanding history.
- Status ownership matters: root service enforces message/notification flow and inactivity behavior.
- Keep the UI and API backed by the same underlying service state instead of forking logic.
- `service.py` is a facade — edit `service/runtime.py` for logic changes.
- `store.py` is a mixin composition — edit the specific `store_*.py` module for store changes.

## ANTI-PATTERNS
- Do not move workflow semantics into CLI agents, MCP clients, or agent runtimes.
- Do not assume exact-once delivery; callback delivery is retry-oriented.
- Do not add prompt-history replay where compact thread state is sufficient.
- Do not change thread terminal-state behavior without updating docs and tests together.
- Do not edit `service.py` or `store.py` directly — they are composition facades.

## COMMANDS
```bash
PYTHONPATH=src python -m core.orchestra_thread.service.main
PYTHONPATH=src python -m core.orchestra_thread.agent_cli --slug human --target orchestra
docker compose --profile test run --rm test
```

## NOTES
- The heaviest file is `service/runtime.py` (1724 lines); next are `agent_cli.py`, store mixins, and `mcp_thread_*` files.
- `tests/test_e2e_mvp.py` and `tests/test_mcp_server.py` are the fastest way to confirm semantic changes.
- MCP handlers are empty (`mcp_handlers.py` = 1 line) — all logic routed through `mcp_thread_*` modules.
