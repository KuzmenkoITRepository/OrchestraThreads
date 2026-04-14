# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-14 Europe/Moscow
**Branch:** master

## OVERVIEW
OrchestraThreads is a Docker-first Python workspace for an autonomy-oriented assistant stack. The repo is service-split on purpose:

- `src/core/orchestra_thread/` owns durable thread identity, delivery, retries, inactivity wakeups, UI/API, and thread MCP tools.
- `src/core/orchestra_agents/` owns manifest loading, validation, Docker lifecycle, scaffolding, and the shared runtime contract for all managed agent backends.
- `src/core/agent_log_analysis/`, `orchestra_memory/`, `task_registry/`, `scheduler_cron/`, and `telegram_bot_listener/` are first-class services now and each has its own child `AGENTS.md`.
- `src/core/events_engine/`, `src/core/telegram_events/`, and `src/core/docker_mcp/` stay documented at root level for now; they are compact edge/integration domains, not large standalone service areas yet.
- LLM routing is externalized through `omniroute` + `wet`.

Read `CODE-STYLE.md` before writing Python. This repo expects `ruff`, `wemake-python-styleguide`, and `mypy --strict` discipline from the first edit.

## STRUCTURE
```text
OrchestraThreads/
├── agents/                          # manifests, prompts, agent-local assets only
├── deploy/                          # Vault/AppRole/env rendering and environment scripts
├── docker/                          # backend-specific Docker assets and patches
├── docs/                            # design notes, WPS governance, rollout plans
├── src/core/
│   ├── agent_log_analysis/          # log ingest/query/correlation service + MCP surface
│   ├── docker_mcp/                  # Docker MCP integration surface
│   ├── events_engine/               # external-event -> agent delivery bridge
│   ├── orchestra_agents/            # manifest registry, Docker lifecycle, backend contract
│   ├── orchestra_memory/            # local memory service + MCP tools
│   ├── orchestra_thread/            # durable thread service, UI/API, MCP tools
│   ├── scheduler_cron/              # job scheduler + executor + events bridge
│   ├── task_registry/               # task service + MCP task tools
│   ├── telegram_bot_listener/       # Telegram Bot API polling + event forwarding
│   └── telegram_events/             # SSE/relay bridge from Telegram-facing systems
├── CODE-STYLE.md                    # shortest path to lint-clean Python here
├── Makefile                         # canonical developer commands
├── docker-compose.yml               # source of truth for local stack, profiles, healthchecks
├── pyproject.toml                   # ruff, mypy, pytest settings
└── setup.cfg                        # flake8/wemake settings and targeted ignores
```

## CHILD GUIDES
- `agents/AGENTS.md`
- `src/core/orchestra_thread/AGENTS.md`
- `src/core/orchestra_agents/AGENTS.md`
- `src/core/agent_log_analysis/AGENTS.md`
- `src/core/orchestra_memory/AGENTS.md`
- `src/core/task_registry/AGENTS.md`
- `src/core/scheduler_cron/AGENTS.md`
- `src/core/telegram_bot_listener/AGENTS.md`

Use the child file when you are already inside that domain. Use this root file for repo-wide boundaries, runtime wiring, and developer workflow.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Thread lifecycle, statuses, retries | `src/core/orchestra_thread/` | main hotspot for durable work identity and delivery semantics |
| Agent registry, manifests, Docker lifecycle | `src/core/orchestra_agents/` | backend contract, scaffold, runtime templates, migrations |
| Log ingestion and correlation | `src/core/agent_log_analysis/` | HTTP runtime + MCP + composed log store |
| Memory-backed retrieval/storage | `src/core/orchestra_memory/` | local store lifecycle + MCP memory tools |
| Task storage and task MCP tools | `src/core/task_registry/` | HTTP task service + composed task store |
| Scheduled job execution | `src/core/scheduler_cron/` | scheduler engine, executor, store, `/healthz` runtime |
| Telegram Bot API polling service | `src/core/telegram_bot_listener/` | long-poll loop, local state, outbound event forwarding |
| Docker MCP integration | `src/core/docker_mcp/` | compact Docker-facing MCP/socket bridge; root-scoped for now |
| External event fan-in | `src/core/events_engine/` | intentionally small bridge; keep rules here unless it grows |
| Telegram relay edge | `src/core/telegram_events/` | SSE/HTTP relay layer; still root-scoped |
| Agent manifests and prompts | `agents/` | definitions only; no core runtime logic |
| Runtime wiring, ports, profiles | `docker-compose.yml` | canonical local topology and service list |
| Quality gates and style constraints | `CODE-STYLE.md`, `pyproject.toml`, `setup.cfg`, `.pre-commit-config.yaml` | enforced, not aspirational |
| Deploy flow and Vault bootstrapping | `deploy/` | AppRole/Vault/env rendering; keep prod on Vault path |
| Refactor governance and rollout notes | `docs/` | WPS plans, boundary docs, friction logs |

## CODE MAP
| Symbol / Entry | Type | Location | Role |
|----------------|------|----------|------|
| `main()` | service entry | `src/core/orchestra_thread/service/main.py` | boots thread service |
| `OrchestraThreadsService` | class | `src/core/orchestra_thread/service/runtime.py` | thread orchestration, delivery, notifications, guide endpoints |
| `main()` | service entry | `src/core/orchestra_agents/service_main.py` | boots lifecycle API |
| `OrchestraAgentsService` | class | `src/core/orchestra_agents/service/runtime.py` | manifest-driven lifecycle service |
| `main()` | service entry | `src/core/agent_log_analysis/service_main.py` | boots log analysis service |
| `AgentLogAnalysisService` | class | `src/core/agent_log_analysis/service_runtime.py` | ingest/query runtime over composed log store |
| `main()` | service entry | `src/core/orchestra_memory/service_main.py` | boots memory service |
| `OrchestraMemoryService` | class | `src/core/orchestra_memory/service_lifecycle.py` | memory lifecycle over local store |
| `main()` | service entry | `src/core/task_registry/service_main.py` | boots task registry service |
| `TaskRegistryService` | class | `src/core/task_registry/service_runtime.py` | task service runtime |
| `main()` | service entry | `src/core/scheduler_cron/service_main.py` | boots scheduler service |
| `SchedulerCronService` | class | `src/core/scheduler_cron/service_runtime.py` | scheduler engine + executor + store orchestration |
| `main()` | service entry | `src/core/telegram_bot_listener/service_main.py` | boots Telegram Bot API listener |
| `TelegramBotListenerService` | class | `src/core/telegram_bot_listener/service_runtime.py` | polling, forwarding, health |
| `main()` | service entry | `src/core/events_engine/service_main.py` | boots external-event bridge |
| `main()` | service entry | `src/core/telegram_events/service_main.py` | boots Telegram relay service |

## CONVENTIONS
- Keep services split. Do not collapse thread orchestration, lifecycle management, memory, scheduling, and Telegram ingress into one runtime.
- `docker-compose.yml` is the source of truth for local stack wiring, ports, healthchecks, and profiles.
- `agents/` contains manifests/prompts/assets only. Backend code lives under `src/core/orchestra_agents/`.
- Edit implementation modules, not facades. In this repo, `service.py`, `store.py`, `router.py`, `accounts.py`, and similar files are often composition or re-export layers.
- Prefer compact thread state and service-owned persistence over replaying giant histories into prompts.
- Put behavior-changing docs next to the module they describe (`src/core/<module>/docs/`) when that domain already owns a child guide.
- Ignore generated or runtime-state paths when mapping architecture: `agents/orchestra/runtime_state/`, other `runtime_state/` trees, and `environments/` copies are not design sources.

## CODE QUALITY ENFORCEMENT

### Mandatory checks
```bash
make format
make lint
make typecheck
make check
docker compose --profile test run --rm test
```

### Enforced rules
- No blanket `# noqa`.
- No `# type: ignore` without a specific, justified reason.
- No lowering lint thresholds or weakening strict typing to get a change through.
- Keep modules, classes, and functions small; split early when locals, branches, or imports grow.
- Use guard clauses and typed payload objects (`dataclass`, `TypedDict`) instead of loose dict plumbing.
- Keep `try` blocks tiny.
- Avoid dumping-ground helpers like `utils.py`.

### Config files that matter
- `CODE-STYLE.md` — repo-specific Python cookbook.
- `pyproject.toml` — `ruff`, `mypy --strict`, `pytest` configuration.
- `setup.cfg` — `flake8` + `wemake` complexity gates and targeted ignores.
- `.pre-commit-config.yaml` — local enforcement before commit.
- `Makefile` — canonical commands; prefer it over handwritten command variants.

## ANTI-PATTERNS
- Do not bypass Docker for the canonical automated test story; this repo expects `docker compose --profile test run --rm test`.
- Do not move `thread_id` ownership into generic agent runtimes or backend adapters.
- Do not treat generated runtime state as architectural evidence.
- Do not let edge services (`events_engine`, `telegram_events`, `telegram_bot_listener`) accumulate thread semantics that belong in `orchestra_thread`.
- Do not let backend-specific logic leak out of `src/core/orchestra_agents/backends/` into manifests or prompts.
- Do not ship broad architectural rewrites as a routine edit; favor incremental, reversible changes.

## COMMANDS
```bash
# Development
make install
make format
make lint
make typecheck
make check
make test

# Core stack via Vault-backed env rendering
bash deploy/deploy-env.sh dev

# User agents
COMPOSE_PROJECT_NAME=orchestrathreads-dev \
  docker compose --profile user-agents --env-file deploy/runtime_env/dev.env \
  up -d odinykt specialist

# Canonical tests
docker compose --profile test run --rm test
```

## DEPLOYMENT

### Vault is mandatory for prod/stg
Production and staging secrets flow through HashiCorp Vault. Use `deploy/deploy-env.sh <env>` so the runtime env is rendered from Vault, used for startup, then removed.

### Compose profiles to remember
| Profile | Purpose |
|---------|---------|
| _(none)_ | core platform stack |
| `vault` | local Vault bootstrap/unseal |
| `user-agents` | manual interactive agents |
| `test` | CI/local automated verification |

## NOTES
- `docs/wps-refactor-governance.md` is the strongest repo-wide statement of forbidden refactor patterns and verification expectations.
- `src/core/events_engine/`, `src/core/telegram_events/`, and `src/core/docker_mcp/` remain root-documented because they are still compact edge/integration domains.
- Root guidance should stay broad. Put service-specific nuance in child `AGENTS.md` files, not here.
