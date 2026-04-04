# LLM PROXY DOMAIN

## OVERVIEW
`llm_proxy` is the compatibility and routing layer for Codex and OpenAI-style traffic, including account rotation, fallback transport, and optional Langfuse tracing.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| HTTP routes | `service.py` | `/healthz`, `/accounts/status`, `/v1/*`, `/codex/v1/*`, `/minimax/v1/*` |
| Boot/config parsing | `service_main.py` | env + CLI -> `ProxyConfig` |
| Routing logic | `router.py`, `transports.py` | upstream selection, cooldowns, fallback behavior |
| Request/response protocol | `protocol.py` | largest logic-heavy file in this module |
| Client helpers | `client_config.py`, `codex_oauth.py` | shared config parsing + auth profile paths |
| Telemetry | `langfuse.py` | grouped by `agent_slug + context_id`, not thread id |
| Tests | `tests/` | service compatibility + optional real backend checks |

## CONVENTIONS
- Add compatibility aliases in the proxy when upstream/client surfaces diverge; do not push that burden into other services.
- Keep routing modes explicit: `managed_auto`, `codex_only`, `minimax_only`.
- Preserve OpenAI-compatible and Codex-compatible contracts side by side.
- Group telemetry by stable agent context, not by thread identity.

## ANTI-PATTERNS
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
- `protocol.py`, `router.py`, and `service.py` are the main complexity hotspots.
- `tests/test_service.py` is the primary compatibility safety net; `tests/test_e2e_real_backends.py` is optional real-upstream coverage.
