# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-03 Europe/Moscow
**Commit:** n/a (not a git repo)
**Branch:** n/a

## OVERVIEW
OrchestraThreads is a Docker-first Python workspace for an autonomous assistant stack built around durable inter-agent threads. The main split is strict: `orchestra_thread` owns thread workflow, `orchestra_agents` owns manifest-driven lifecycles, and `llm_proxy` owns model routing.

## STRUCTURE
```text
OrchestraThreads/
├── src/core/orchestra_thread/   # durable thread service, UI, MCP surface
├── src/core/orchestra_agents/   # manifest registry, Docker lifecycle, runtime contract
├── src/core/llm_proxy/          # OpenAI/Codex-compatible routing + Langfuse hooks
├── src/core/events_engine/      # external-event -> agent delivery bridge
├── src/core/telegram_events/    # Telegram ingestion -> secretary/event bridge
├── agents/                      # local manifests and example runtimes
├── docs/                        # repo-level design notes and refactor plans
└── docker-compose.yml           # source of truth for local stack and tests
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Thread lifecycle, statuses, retries | `src/core/orchestra_thread/` | `service.py`, `store.py`, `mcp_server.py` are the hotspots |
| Agent registry, scaffold, Docker driver | `src/core/orchestra_agents/` | lifecycle service only; not thread semantics |
| Model routing, fallbacks, telemetry | `src/core/llm_proxy/` | HTTP compatibility aliases live here |
| External event fan-in | `src/core/events_engine/` | minimal bridge into running agents |
| Telegram ingress | `src/core/telegram_events/` | explicitly non-thread-native edge service |
| Agent manifests and prompts | `agents/` | runtime examples, mux configs, system prompts |
| Stack wiring and healthchecks | `docker-compose.yml` | canonical ports, env, service dependencies |

## CODE MAP
| Symbol / Entry | Type | Location | Role |
|----------------|------|----------|------|
| `main()` | service entry | `src/core/orchestra_thread/service_main.py` | boots thread service + aiohttp app |
| `OrchestraThreadsService` | class | `src/core/orchestra_thread/service.py` | threads, agents, notifications, guide endpoints |
| `main()` | service entry | `src/core/orchestra_agents/service_main.py` | boots lifecycle API |
| `OrchestraAgentsService` | class | `src/core/orchestra_agents/service.py` | manifest registry + agent control |
| `StandardAgentApplication` routes | runtime contract | `src/core/orchestra_agents/runtime/app.py` | `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context` |
| `main()` | service entry | `src/core/llm_proxy/service_main.py` | parses env/CLI into `ProxyConfig` |
| `LLMProxyService` | class | `src/core/llm_proxy/service.py` | OpenAI/Codex-compatible API surface |
| `main()` | service entry | `src/core/events_engine/service_main.py` | starts external event bridge |
| `main()` | service entry | `src/core/telegram_events/service_main.py` | starts Telegram listener |

## CONVENTIONS
- Preserve the module split; do not fold thread orchestration, agent lifecycle, and LLM routing into one service.
- Favor compact thread state and on-demand expansion over replaying full histories into prompts.
- Keep services HTTP-first: explicit JSON contracts, `/healthz`, and observable state.
- Treat `agents/` as manifest-driven runtime examples, not as the place to re-implement core service logic.
- Put behavior-changing docs next to the module they describe (`src/core/<module>/docs/`).

## ANTI-PATTERNS
- Do not treat anything except `docker-compose.yml` as the source of truth for local runtime wiring.
- Do not bypass Docker for the primary automated test story; canonical verification is `docker compose --profile test run --rm test`.
- Do not move thread ownership into agent runtimes or `agent-mux`; `thread_id` semantics stay in `orchestra_thread`.
- Do not expand specialist access by default; the architecture assumes minimal context and explicit escalation.
- Do not ship major architectural changes as routine edits; incremental, reversible improvements are the default.

## UNIQUE STYLES
- Product direction is autonomy-first, but with service-level observability, healthchecks, and rollback discipline.
- The repo mixes service code with runnable agent examples; distinguish “platform service” changes from “agent behavior” changes.
- Example agents are expected to communicate outward through thread tools/status flows, not free-form assistant prose.

## COMMANDS
```bash
docker compose up --build -d postgres orchestra-threads orchestra-agents llm-proxy
docker compose run --rm --use-aliases secretary
docker compose run --rm --use-aliases orchestra
docker compose --profile test run --rm test
docker compose down
```

## NOTES
- Ignore `agents/orchestra/runtime_state/` during repo sweeps; it contains generated state and unreadable paths.
- `src/core/events_engine/` and `src/core/telegram_events/` are small edge services, so keep their rules in root unless they grow.
- The root file is intentionally short; child `AGENTS.md` files below carry only domain-specific deltas.
