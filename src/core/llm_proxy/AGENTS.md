# LLM PROXY DOMAIN

## ⚠️ DEPRECATED
This service is deprecated and scheduled for removal. See `DEPRECATED.md`. Do not expand with new product logic; prefer migration and containment.

## OVERVIEW
`llm_proxy` is the compatibility and routing layer for Codex and OpenAI-style traffic, including account rotation, fallback transport, and optional Langfuse tracing. After refactoring, heavy logic lives in `_*_impl.py` files; public modules are thin facades using `importlib` re-exports.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| HTTP routes | `service.py` | `/healthz`, `/accounts/status`, `/v1/*`, `/codex/v1/*`, `/minimax/v1/*` |
| Boot/config parsing | `service_main.py` | env + CLI -> `ProxyConfig` |
| Routing logic | `router.py` → `router_runtime.py` → `_router_runtime_impl.py` | facade chain; edit `_router_runtime_impl.py` |
| Request/response protocol | `protocol.py` | largest logic-heavy file in this module |
| Account management | `accounts.py` → `_accounts_impl.py` → `_accounts_core.py` | facade chain |
| Client helpers | `client_config.py`, `codex_oauth.py` | shared config parsing + auth profile paths |
| Telemetry | `langfuse.py` → `_langfuse_impl.py` → `_langfuse_runtime.py` | facade chain; grouped by `agent_slug + context_id` |
| Streaming | `transports_stream.py` | streaming transport layer (new) |
| Tests | `tests/` | service compatibility + optional real backend checks |

## CONVENTIONS
- Add compatibility aliases in the proxy when upstream/client surfaces diverge; do not push that burden into other services.
- Keep routing modes explicit: `managed_auto`, `codex_only`, `minimax_only`.
- Preserve OpenAI-compatible and Codex-compatible contracts side by side.
- Group telemetry by stable agent context, not by thread identity.
- Public modules (`router.py`, `accounts.py`, `langfuse.py`) are re-export facades — edit the `_*_impl.py` backing files.
- This module is **excluded from ruff, mypy, and flake8** checks (deprecated).

## ANTI-PATTERNS
- Do not expand this service with new product logic — it is deprecated.
- Do not leak proxy-specific routing concerns into `orchestra_thread` or agent manifests beyond configuration.
- Do not remove compatibility endpoints casually; tests rely on alias behavior.
- Do not couple Langfuse grouping to `thread_id`.
- Do not hardcode a single upstream account path when rotation/fallback is part of the design.

## COMMANDS
```bash
PYTHONPATH=src python -m core.llm_proxy.service_main
docker compose restart llm-proxy
docker compose --profile test run --rm test
```

## NOTES
- `_router_runtime_impl.py` (routing), `protocol.py` (protocol), and `service.py` (HTTP) are the main complexity hotspots.
- `tests/test_service.py` is the primary compatibility safety net; `tests/test_e2e_real_backends.py` is optional real-upstream coverage.
- Facade files use `importlib.import_module` and `sys.modules` tricks — follow the chain to find actual implementation.
