# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-04 Europe/Moscow
**Commit:** dede013
**Branch:** master

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

## CODE QUALITY ENFORCEMENT

### CI/CD Checks (MANDATORY)
All code MUST pass these checks before commit:

```bash
make check          # Run all checks (format + lint + typecheck)
make format         # Auto-format code with ruff
make lint           # Run ruff + wemake-python-styleguide
make typecheck      # Run mypy --strict
```

### Pre-commit Hooks
Installed automatically via `make install`. Runs on every `git commit`:
1. **ruff** — Fast linter and formatter (auto-fixes)
2. **mypy --strict** — Strict type checking (no Any, all functions typed)
3. **wemake-python-styleguide** — Strictest Python linter (complexity, nesting, best practices)
4. **pre-commit-hooks** — Trailing whitespace, EOF, YAML validation, large files

### CRITICAL RULES (ZERO TOLERANCE)

**NEVER bypass checks:**
- ❌ NO `# type: ignore` without explicit justification in comment
- ❌ NO `# noqa` without specific error code (e.g., `# noqa: WPS220`)
- ❌ NO `--no-verify` on git commit
- ❌ NO disabling pre-commit hooks
- ❌ NO committing code that fails `make check`

**Type safety:**
- ✅ ALL functions must have type annotations
- ✅ NO `Any` types without explicit justification
- ✅ Use `typing` module for complex types
- ✅ Prefer `TypedDict` over `dict[str, Any]`

**Code quality:**
- ✅ Max function complexity: 12 (cognitive complexity)
- ✅ Max nesting depth: 20
- ✅ Max function length: reasonable (wemake enforces)
- ✅ NO magic numbers — use named constants
- ✅ NO mutable default arguments

**When checks fail:**
1. Fix the root cause, don't suppress warnings
2. If suppression is truly needed, add inline comment explaining WHY
3. Prefer refactoring over suppression
4. Ask for review if unsure

### Setup
```bash
make install        # Install deps + pre-commit hooks
make check          # Verify everything works
```

## ANTI-PATTERNS
- Do not treat anything except `docker-compose.yml` as the source of truth for local runtime wiring.
- Do not bypass Docker for the primary automated test story; canonical verification is `docker compose --profile test run --rm test`.
- Do not move thread ownership into agent runtimes or `agent-mux`; `thread_id` semantics stay in `orchestra_thread`.
- Do not expand specialist access by default; the architecture assumes minimal context and explicit escalation.
- Do not ship major architectural changes as routine edits; incremental, reversible improvements are the default.
- **Do not bypass code quality checks** — see CODE QUALITY ENFORCEMENT section above.

## UNIQUE STYLES
- Product direction is autonomy-first, but with service-level observability, healthchecks, and rollback discipline.
- The repo mixes service code with runnable agent examples; distinguish "platform service" changes from "agent behavior" changes.
- Example agents are expected to communicate outward through thread tools/status flows, not free-form assistant prose.
- Code quality is enforced via automated checks — no exceptions without explicit justification.

## COMMANDS
```bash
# Development
make install                    # Setup environment
make check                      # Run all quality checks
make format                     # Format code
make lint                       # Run linters
make typecheck                  # Type check with mypy
make test                       # Run tests in Docker
make clean                      # Clean cache files

# Docker stack
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
- All code must pass `make check` before commit — no exceptions.
