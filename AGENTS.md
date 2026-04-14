# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-14 Europe/Moscow
**Branch:** master

## OVERVIEW
OrchestraThreads = Docker-first Python workspace for autonomy stack. Repo split by service on purpose.

- `src/core/orchestra_thread/` owns durable `thread_id`, delivery, retries, inactivity wakeups, UI/API, thread MCP.
- `src/core/orchestra_agents/` owns manifests, validation, Docker lifecycle, scaffolding, migrations, shared managed-agent runtime contract.
- `src/core/agent_log_analysis/`, `orchestra_memory/`, `task_registry/`, `scheduler_cron/`, `telegram_bot_listener/` each own standalone service domain + child `AGENTS.md`.
- `src/core/events_engine/`, `src/core/telegram_events/`, `src/core/docker_mcp/` stay root-scoped for now. Edge/integration domains without child guides yet.
- LLM routing runs through `orchestra-omniroute` + `orchestra-wet` in `docker-compose.yml`.

Read `CODE-STYLE.md` before Python edits. Repo expects `ruff`, `wemake-python-styleguide`, `mypy --strict` from first change.

## STRUCTURE
```text
OrchestraThreads/
├── agents/                          # manifests, prompts, agent-local assets only
├── deploy/                          # Vault/AppRole/env rendering, env scripts
├── docker/                          # backend-specific Docker assets, patches
├── docs/                            # design notes, WPS governance, rollout plans
├── src/core/
│   ├── agent_log_analysis/          # log ingest/query/correlation service + MCP
│   ├── docker_mcp/                  # Docker MCP integration surface
│   ├── events_engine/               # external event -> agent delivery bridge
│   ├── orchestra_agents/            # manifest registry, Docker lifecycle, backend contract
│   ├── orchestra_memory/            # local memory service + MCP tools
│   ├── orchestra_thread/            # durable thread service, UI/API, MCP tools
│   ├── scheduler_cron/              # scheduler + executor + events bridge
│   ├── task_registry/               # task service + MCP task tools
│   ├── telegram_bot_listener/       # Telegram polling + event forwarding
│   └── telegram_events/             # Telegram relay/listener edge service
├── CODE-STYLE.md                    # shortest path to lint-clean Python
├── Makefile                         # canonical commands
├── docker-compose.yml               # source of truth for stack wiring
├── pyproject.toml                   # ruff, mypy, pytest settings
└── setup.cfg                        # flake8/wemake gates, targeted ignores
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

Use child guide inside domain. Use root guide for repo boundaries, stack wiring, workflow.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Thread lifecycle, retries, statuses | `src/core/orchestra_thread/` | main semantic hotspot for durable work identity |
| Agent registry, manifests, Docker lifecycle | `src/core/orchestra_agents/` | backend contract, scaffold, runtime templates, migrations |
| Log ingest, query, correlation | `src/core/agent_log_analysis/` | HTTP runtime + MCP + composed log store |
| Memory retrieval/storage | `src/core/orchestra_memory/` | local store lifecycle + MCP memory tools |
| Task persistence + MCP task tools | `src/core/task_registry/` | task service + composed task store |
| Scheduled jobs | `src/core/scheduler_cron/` | scheduler engine, executor, store, `/healthz` |
| Telegram Bot API polling | `src/core/telegram_bot_listener/` | long poll, local state, outbound forwarding |
| Docker MCP edge | `src/core/docker_mcp/` | compact Docker-facing bridge |
| External event fan-in | `src/core/events_engine/` | small bridge; keep root-scoped unless it grows |
| Telegram relay edge | `src/core/telegram_events/` | Telegram relay/listener HTTP edge |
| Agent manifests + prompts | `agents/` | definitions only; no core runtime logic |
| Stack wiring, ports, profiles | `docker-compose.yml` | canonical local topology |
| Quality gates | `CODE-STYLE.md`, `pyproject.toml`, `setup.cfg`, `.pre-commit-config.yaml` | enforced, not aspirational |
| Deploy flow + Vault bootstrapping | `deploy/` | prod/stg stay on Vault path |
| Refactor governance | `docs/` | WPS plans, boundary docs, friction logs |

## CODE MAP
| Symbol / Entry | Type | Location | Role |
|----------------|------|----------|------|
| `main()` | service entry | `src/core/orchestra_thread/service/main.py` | boot thread service |
| `OrchestraThreadsService` | class | `src/core/orchestra_thread/service/runtime.py` | thread orchestration, delivery, notifications, guide endpoints |
| `main()` | service entry | `src/core/orchestra_agents/service_main.py` | boot lifecycle API |
| `OrchestraAgentsService` | class | `src/core/orchestra_agents/service/runtime.py` | manifest-driven lifecycle service |
| `main()` | service entry | `src/core/agent_log_analysis/service_main.py` | boot log analysis service |
| `AgentLogAnalysisService` | class | `src/core/agent_log_analysis/service_runtime.py` | ingest/query runtime over composed log store |
| `main()` | service entry | `src/core/orchestra_memory/service_main.py` | boot memory service |
| `OrchestraMemoryService` | class | `src/core/orchestra_memory/service_lifecycle.py` | memory lifecycle over local store |
| `main()` | service entry | `src/core/task_registry/service_main.py` | boot task registry service |
| `TaskRegistryService` | class | `src/core/task_registry/service_runtime.py` | task service runtime |
| `main()` | service entry | `src/core/scheduler_cron/service_main.py` | boot scheduler service |
| `SchedulerCronService` | class | `src/core/scheduler_cron/service_runtime.py` | scheduler engine + executor + store orchestration |
| `main()` | service entry | `src/core/telegram_bot_listener/service_main.py` | boot Telegram listener |
| `TelegramBotListenerService` | class | `src/core/telegram_bot_listener/service_runtime.py` | polling, forwarding, health |
| `main()` | service entry | `src/core/events_engine/service_main.py` | boot external-event bridge |
| `main()` | service entry | `src/core/telegram_events/service_main.py` | boot Telegram relay service |

## CONVENTIONS
- Keep services split. Do not collapse thread orchestration, lifecycle, memory, scheduling, Telegram ingress into one runtime.
- `docker-compose.yml` = source of truth for local stack wiring, ports, healthchecks, profiles.
- `agents/` holds manifests/prompts/assets only. Backend code lives under `src/core/orchestra_agents/`.
- Edit impl modules, not facades. Here `service.py`, `store.py`, `router.py`, `accounts.py` often compose or re-export.
- Prefer compact thread state + service-owned persistence over giant prompt replay.
- Put behavior-changing docs next to owning module when domain already has child guide.
- Ignore generated paths when mapping architecture: `agents/orchestra/runtime_state/`, other `runtime_state/` trees, `environments/` copies are ops artifacts, not design source.

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
- No `# type: ignore` without specific justified reason.
- No lowering lint thresholds or weakening strict typing.
- Keep modules, classes, fns small. Split early when locals, branches, imports grow.
- Prefer guard clauses + typed payloads (`dataclass`, `TypedDict`) over loose dict plumbing.
- Keep `try` blocks tiny.
- Avoid dump helpers like `utils.py`.

### Config files that matter
- `CODE-STYLE.md` — repo-specific Python cookbook.
- `pyproject.toml` — `ruff`, `mypy --strict`, `pytest` config.
- `setup.cfg` — `flake8` + `wemake` gates, targeted ignores.
- `.pre-commit-config.yaml` — local enforcement.
- `Makefile` — canonical commands.

## ANTI-PATTERNS
- Do not bypass Docker for canonical automated tests. Repo expects `docker compose --profile test run --rm test`.
- Do not move `thread_id` ownership into generic runtimes or backend adapters.
- Do not treat generated runtime state as architecture evidence.
- Do not let edge services (`events_engine`, `telegram_events`, `telegram_bot_listener`) absorb thread semantics from `orchestra_thread`.
- Do not leak backend-specific logic out of `src/core/orchestra_agents/backends/` into manifests or prompts.
- Do not ship broad architecture rewrites as routine edit. Favor incremental, reversible change.

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
Prod + stg secrets flow through HashiCorp Vault. Use `deploy/deploy-env.sh <env>` so runtime env renders from Vault, starts services, then gets removed.

### Compose profiles to remember
| Profile | Purpose |
|---------|---------|
| _(none)_ | core platform stack |
| `vault` | local Vault bootstrap/unseal |
| `user-agents` | manual interactive agents |
| `test` | CI/local automated verification |

## NOTES
- `docs/wps-refactor-governance.md` = strongest repo-wide refactor-boundary + verification guide.
- `src/core/events_engine/`, `src/core/telegram_events/`, `src/core/docker_mcp/` stay root-documented because they still have no child guides.
- Keep root guide broad. Put service-specific nuance in child `AGENTS.md` files.
