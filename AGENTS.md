# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-06 Europe/Moscow
**Commit:** da87ce3
**Branch:** master

## OVERVIEW
OrchestraThreads is a Docker-first Python workspace for an autonomous assistant stack built around durable inter-agent threads. The main split is strict: `orchestra_thread` owns thread workflow, `orchestra_agents` owns manifest-driven lifecycles and the `agent_mux_runtime` subsystem. LLM routing is handled by external `omniroute` + `wet` services. `telegram_mcp` provides MCP-based Telegram messaging for agents.

## STRUCTURE
```text
OrchestraThreads/
├── src/core/orchestra_thread/   # durable thread service, UI, MCP surface (36 py files)
├── src/core/orchestra_agents/   # manifest registry, Docker lifecycle, runtime contract
│   └── agent_mux_runtime/       # 29-file multiplexed agent runtime subsystem
├── src/core/events_engine/      # external-event -> agent delivery bridge (minimal)
├── src/core/events_engine/      # external-event -> agent delivery bridge (minimal)
├── src/core/telegram_events/    # Telegram ingestion -> secretary/event bridge
├── src/telegram_mcp/            # MCP server for Telegram messaging via Telethon
├── agents/                      # local manifests and example runtimes
├── docs/                        # repo-level design notes and refactor plans
├── docker/                      # build patches (agent-mux binary)
├── Dockerfile                   # main service image
├── Dockerfile.agent_mux_runtime # Go agent-mux binary + Python runtime
├── Dockerfile.agent_runtime     # lightweight agent runtime image
└── docker-compose.yml           # source of truth for local stack and tests
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Thread lifecycle, statuses, retries | `src/core/orchestra_thread/` | `service_runtime.py` (1724 lines) is the main hotspot |
| Store layer (Postgres) | `src/core/orchestra_thread/store*.py` | decomposed into 7 mixin files via `store.py` |
| MCP tool surface | `src/core/orchestra_thread/mcp_*.py` | 12+ files: routing, send, status, views, context |
| HTTP handlers | `src/core/orchestra_thread/http_handlers.py` | read/write handler classes |
| Agent registry, scaffold, Docker | `src/core/orchestra_agents/` | `service.py` delegates to `service_routes.py` + `service_state.py` |
| Agent mux runtime | `src/core/orchestra_agents/agent_mux_runtime/` | queue, dispatch, state, codex config, bootstrap |
| External event fan-in | `src/core/events_engine/` | minimal bridge into running agents |
| Telegram ingress | `src/core/telegram_events/` | edge service; non-thread-native |
| Telegram MCP server | `src/telegram_mcp/` | stdio MCP for `send_telegram_message`; shares Telethon session with telegram_events |
| Agent manifests and prompts | `agents/` | runtime examples, mux configs, system prompts |
| Stack wiring and healthchecks | `docker-compose.yml` | canonical ports, env, service dependencies |

## CODE MAP
| Symbol / Entry | Type | Location | Role |
|----------------|------|----------|------|
| `main()` | service entry | `src/core/orchestra_thread/service_main.py` | boots thread service + aiohttp app |
| `OrchestraThreadsService` | class | `src/core/orchestra_thread/service_runtime.py` | threads, agents, notifications, guide endpoints (1724 lines) |
| `build_app()` | function | `src/core/orchestra_thread/service_runtime.py` | wires HTTP routes via `http_handlers.py` |
| `ThreadStore` | class | `src/core/orchestra_thread/store.py` | mixin composition of 7 store modules |
| `OrchestraThreadsMCPServer` | class | `src/core/orchestra_thread/mcp_server.py` | compact MCP server delegating to `mcp_thread_*` tools |
| `HttpReadHandlers` / `HttpWriteHandlers` | classes | `src/core/orchestra_thread/http_handlers.py` | HTTP endpoint handler classes |
| `main()` | service entry | `src/core/orchestra_agents/service_main.py` | boots lifecycle API |
| `OrchestraAgentsService` | class | `src/core/orchestra_agents/service.py` | manifest registry + agent control |
| `ServiceState` | dataclass | `src/core/orchestra_agents/service_state.py` | registry + driver + lock |
| `StandardAgentApplication` | class | `src/core/orchestra_agents/runtime/app.py` | `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context` |
| `run_backend()` | function | `src/core/orchestra_agents/agent_mux_runtime/bootstrap.py` | mux runtime entry point |
| `main()` | service entry | `src/core/events_engine/service_main.py` | starts external event bridge |
| `main()` | service entry | `src/core/telegram_events/service_main.py` | starts Telegram listener |
| `main()` | entry | `src/telegram_mcp/__main__.py` | stdio MCP server for Telegram messaging |

## CONVENTIONS
- Preserve the module split; do not fold thread orchestration, agent lifecycle, and LLM routing into one service.
- Favor compact thread state and on-demand expansion over replaying full histories into prompts.
- Keep services HTTP-first: explicit JSON contracts, `/healthz`, and observable state.
- Treat `agents/` as manifest-driven runtime examples, not as the place to re-implement core service logic.
- Put behavior-changing docs next to the module they describe (`src/core/<module>/docs/`).
- Facade files (`service.py`, `store.py`, `router.py`, `accounts.py`, `langfuse.py`) re-export from `_*_impl.py` or `*_runtime.py` — edit the implementation files, not the facades.
- Any human or subagent that writes Python in this repo must read `CODE-STYLE.md` first and follow it as the shortest lint-passing cookbook.

## CODE QUALITY ENFORCEMENT

## Copy-paste prompt for subagents

Use this block when delegating Python code changes to a subagent.

```text
Before writing code, read `AGENTS.md` and `CODE-STYLE.md`.

Your goal is to produce code that passes `ruff`, `wemake-python-styleguide`, and `mypy --strict` on the first try.

Hard rules:
- do not bypass linters or hooks
- do not use blanket `# noqa`
- do not use `# type: ignore` without explicit justification
- do not change lint thresholds or config to make code pass
- fix root causes by simplifying code

Code shape requirements:
- keep modules small and single-purpose
- keep classes thin
- keep functions small and single-purpose
- split early when imports, module members, methods, locals, loops, branches, or nesting start to grow
- use guard clauses instead of deep nesting
- keep `try` blocks tiny: wrap only the risky operation
- use typed objects (`dataclass`, `TypedDict`) instead of long argument lists or loose dicts
- use package-correct imports for sibling modules
- avoid clever unpacking and dense one-line logic

Common failures to avoid explicitly:
- `WPS221` high Jones Complexity
- `WPS202` too many module members
- `WPS300` local folder import
- `WPS414` incorrect unpacking target
- `WPS229` try body too long
- `WPS214` too many methods
- `WPS210` too many local variables
- `WPS231` too much cognitive complexity
- `WPS201` too many imports
- `WPS211` too many arguments

Preferred implementation strategy:
1. Match existing nearby patterns.
2. Write the smallest typed version first.
3. If a file grows, split by operational role, not into generic helpers.
4. If a class grows, move stateless logic into helper modules.
5. If a function grows, split by phase: validate -> transform -> persist/return.
6. If a line gets dense, split the decision into helpers.

Do not create `utils.py` / `helpers.py` dumping grounds.
Do not hide problems with suppressions.
If the code is only valid after a bypass, it is not done.
```

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
- ❌ NO changing linter thresholds or configuration to make new code pass

**Type safety:**
- ✅ ALL functions must have type annotations
- ✅ NO `Any` types without explicit justification
- ✅ Use `typing` module for complex types
- ✅ Prefer `TypedDict` over `dict[str, Any]`

**Code quality:**
- ✅ Repo complexity gate: `max-complexity = 10` in `setup.cfg`
- ✅ WSP-style constraints apply: keep functions small, nesting shallow, locals low, and split early
- ✅ Function length must stay reasonable; prefer decomposition over large handlers
- ✅ NO magic numbers — use named constants
- ✅ NO mutable default arguments
- ✅ Split early when functions accumulate too many locals, loops, or branches; see `CODE-STYLE.md`

**When checks fail:**
1. Fix the root cause, don't suppress warnings
2. If suppression is truly needed, add inline comment explaining WHY
3. Prefer refactoring over suppression
4. Ask for review if unsure

### Mandatory reading for code-writing agents

- `CODE-STYLE.md` is required reading before writing Python.
- Delegated subagents that implement code must be told to follow `CODE-STYLE.md`.
- When delegating code changes, include the requirement to keep modules, classes, and functions small; reduce imports, locals, loop count, branch density, and avoid linter bypasses.
- The most common real agent failures in this repo family are `WPS221`, `WPS202`, `WPS300`, `WPS414`, `WPS229`, `WPS214`, `WPS210`, `WPS231`, `WPS201`, and `WPS211`; code-writing prompts should explicitly guard against them.
- Treat `CODE-STYLE.md` as the minimal context file for ChatGPT/Sonnet-style agents that need to produce lint-clean code quickly.


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
- Heavy files use decomposition: `service_runtime.py` delegates to `http_handlers.py`, `store.py` composes 7 mixin stores, MCP logic is split across 12+ `mcp_thread_*` modules.

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
docker compose run --rm --use-aliases secretary
docker compose run --rm --use-aliases orchestra
docker compose --profile test run --rm test
docker compose down
```

## NOTES
- Ignore `agents/orchestra/runtime_state/` during repo sweeps; it contains generated state and unreadable paths.
- `src/core/events_engine/` and `src/core/telegram_events/` are small edge services, so keep their rules in root unless they grow.
- `src/telegram_mcp/` is a standalone MCP server sharing Telethon auth with `telegram_events` — not a core service.
- The root file is intentionally short; child `AGENTS.md` files below carry only domain-specific deltas.
- All code must pass `make check` before commit — no exceptions.
- `CODE-STYLE.md` is the authoritative quick cookbook for writing new Python that passes repo linters without bypasses.
