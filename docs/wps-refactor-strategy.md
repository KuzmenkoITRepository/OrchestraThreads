# WPS refactor strategy (excluding `omniroute` + `wet`)

**Historical note:** `llm-proxy` has been replaced by `omniroute` + `wet`.

## Scope

This document defines the repository-wide strategy for eliminating the remaining
`wemake-python-styleguide` debt **without** treating `src/core/omniroute/` or
`src/core/wet/` as active refactoring targets.

`omniroute` + `wet` are the active replacement, so the old `llm-proxy` path is
excluded from the active remediation plan. The goal of this strategy is
to make the **rest of the repository** systematically maintainable and capable of
reaching a green WPS state through architectural refactoring rather than
file-by-file cosmetic cleanup.

## Measured active debt

Current WPS count after excluding `src/core/omniroute/**` and `src/core/wet/**`:

- total active WPS debt: **443**
- `tests`: **163**
- `templates`: **92**
- `agents-runtime`: **67**
- `orchestra_thread`: **56**
- `telegram_mcp`: **34**
- `orchestra_agents`: **27**
- `telegram_events`: **4**

Most common active rules:

- `WPS221`: 46
- `WPS210`: 42
- `WPS231`: 27
- `WPS229`: 25
- `WPS118`: 25
- `WPS220`: 21
- `WPS501`: 19
- `WPS504`: 18
- `WPS214`: 18
- `WPS213`: 18

Top active files:

1. `src/core/orchestra_thread/tests/test_e2e_mvp.py` — 41
2. `agents/sgr/agent_runtime/backend.py` — 40
3. `src/core/orchestra_agents/tests/test_agent_mux_template.py` — 35
4. `src/core/orchestra_agents/templates/agent_mux/agent_runtime/state.py` — 32
5. `src/core/orchestra_agents/templates/agent_mux/agent_runtime/backend.py` — 31
6. `src/core/orchestra_thread/tests/test_mcp_server.py` — 24
7. `src/core/orchestra_thread/store.py` — 19
8. `src/telegram_mcp/mcp_server.py` — 17
9. `src/telegram_mcp/telegram_client.py` — 16
10. `src/core/orchestra_agents/templates/agent_mux/agent_runtime/dispatch.py` — 14

## Core diagnosis

The remaining WPS debt is not one single problem. It is a combination of four
different debt classes that must be handled differently:

### 1. Active production-core debt

This is the debt that reflects actual architectural concentration in maintained
service code:

- `src/core/orchestra_thread/**`
- `src/core/orchestra_agents/**`
- `src/telegram_mcp/**`
- `src/core/telegram_events/**`
- `src/core/events_engine/**`

In this class, WPS signals are meaningful. The dominant failures (`WPS221`,
`WPS210`, `WPS231`, `WPS214`, `WPS229`) mostly indicate over-concentrated
responsibilities, large orchestration units, and procedural aggregation.

### 2. Template/scaffold debt

`src/core/orchestra_agents/templates/**` is not throwaway code, but it is also
not service-core. It is scaffold source code. Treating it as identical to
production service modules leads to wasted effort and misleading prioritization.

### 3. Example-runtime debt

`agents/**` contains runnable examples. These examples currently duplicate a
substantial portion of runtime complexity instead of reusing a shared core
runtime layer.

### 4. Integration-test harness debt

The largest test files are integration harnesses, not narrow unit tests. Their
current WPS debt comes mostly from repeated setup, inline fake services, and
scenario-heavy orchestration code living directly inside test files.

## Main anti-pattern to stop

The repository already shows a repeated pattern of solving WPS locally by
turning public modules into thin wrappers while moving complexity into
`*_impl.py`, `*_runtime.py`, or similarly named files.

That pattern must **not** be used as the default remediation technique for the
remaining active scope.

It is acceptable to create a facade file only when both conditions are true:

1. the split reduces coupling and clarifies module responsibilities;
2. the split reduces total subsystem complexity instead of merely moving WPS
   violations into another file.

If a split only changes where the complexity lives, it is a cosmetic change and
must be rejected.

## System strategy

The active plan is to reduce WPS debt by removing duplicated runtime logic,
decomposing operational service roles, and extracting shared test harnesses.

The work must proceed in this order.

## Phase 0 — active scope and governance

### Goal

Create a stable working frame so the campaign measures the right debt.

### Required outcomes

- Exclude `src/core/omniroute/**` and `src/core/wet/**` from the active WPS remediation target.
- Track active debt separately from deprecated debt.
- Explicitly forbid new cosmetic shim layers as a default lint tactic.

### Why first

Without this step, progress reporting will remain distorted by deprecated code
and by cosmetic file motion.

## Phase 1 — unify `agent_mux` runtime logic inside `orchestra_agents`

### Goal

Eliminate duplicated runtime complexity shared across templates and example
agents.

### Diagnosis

The heaviest non-`omniroute`/`wet` debt is concentrated around the `agent_mux`
template/runtime shape:

- `src/core/orchestra_agents/templates/agent_mux/agent_runtime/backend.py`
- `src/core/orchestra_agents/templates/agent_mux/agent_runtime/state.py`
- `src/core/orchestra_agents/templates/agent_mux/agent_runtime/dispatch.py`
- `agents/sgr/agent_runtime/backend.py`
- related tests in `src/core/orchestra_agents/tests/`

This is the highest-leverage target because one architectural fix reduces debt
in templates, example runtimes, and tests at the same time.

### Target shape

Create a shared runtime layer inside `src/core/orchestra_agents/`, for example:

- `agent_mux_runtime/state_store.py`
- `agent_mux_runtime/dispatch_engine.py`
- `agent_mux_runtime/prompt_builder.py`
- `agent_mux_runtime/worker_backend.py`
- `agent_mux_runtime/models.py`

The template and example agents should become thin adapters around these shared
primitives rather than owning the queue/state/dispatch engine themselves.

### Success criteria

- Runtime logic is implemented once in shared core code.
- Template files become thinner and mostly declarative.
- Example agents reuse the same runtime primitives instead of carrying copies.
- WPS debt falls simultaneously in `templates`, `agents-runtime`, and related
  runtime tests.

## Phase 2 — decompose `orchestra_thread` by operational responsibility

### Goal

Reduce service-level procedural aggregation in `orchestra_thread`.

### Diagnosis

The remaining debt in `orchestra_thread` is smaller in raw count than the
template/runtime area, but it is production-critical debt. The hotspots point to
overloaded service coordination and broad handler modules:

- `store.py`
- `mcp_handlers.py`
- integration harnesses in `tests/`

### Target shape

Split by role, not by line count:

- delivery orchestration
- inactivity watching
- agent registration / heartbeat management
- thread/message/notification operations
- MCP tool families
- HTTP handler wiring

`mcp_handlers.py` should be decomposed into coherent tool families instead of
remaining a single procedural aggregator.

### Success criteria

- each module has a single operational reason to change;
- orchestration logic is easier to locate by concern;
- WPS reductions come from smaller responsibility surfaces, not wrapper files.

## Phase 3 — redesign test harnesses, not just test methods

### Goal

Reduce WPS in tests by extracting shared orchestration infrastructure.

### Diagnosis

Large test files such as:

- `src/core/orchestra_thread/tests/test_e2e_mvp.py`
- `src/core/orchestra_thread/tests/test_mcp_server.py`
- `src/core/orchestra_agents/tests/test_agent_mux_template.py`
- `src/core/orchestra_agents/tests/test_sgr_example.py`

currently embed fake services, setup logic, transport helpers, and scenario
builders inline. That creates test debt that mirrors missing shared test support.

### Target shape

Extract shared harness pieces into dedicated support modules / fixtures:

- fake agents
- async request helpers
- backend startup helpers
- runtime capture helpers
- scenario builders

The first objective is to remove duplicated orchestration setup. Cosmetic cleanup
such as shortening descriptive test names is lower priority.

### Success criteria

- repeated setup code moves out of top-level test files;
- test files become more scenario-focused;
- remaining complexity reflects actual integration breadth rather than repeated
  harness boilerplate.

## Phase 4 — finish `telegram_mcp` after core simplification

### Goal

Resolve the remaining edge-service debt after shared runtime and service-core
cleanup are complete.

### Diagnosis

`src/telegram_mcp/mcp_server.py` and `src/telegram_mcp/telegram_client.py`
still carry moderate WPS debt, but they are smaller and lower leverage than the
runtime/template duplication problem.

### Target shape

Separate:

- Telegram API interaction,
- request/command handling,
- normalization/parsing,
- edge-specific retry/session concerns.

### Success criteria

- lower WPS in `telegram_mcp` without expanding surface area;
- clearer split between I/O and request interpretation.

## Phase 5 — final active-scope WPS sweep

Only after the previous phases are complete should the repository move into a
true cleanup pass targeting remaining local issues such as:

- `WPS221`
- `WPS210`
- `WPS231`
- `WPS229`
- `WPS211`
- `WPS504`
- `WPS338`

At that point these fixes should be local and boring. If they still require
large restructuring, an earlier phase was incomplete.

## Execution rules

1. Do not begin with test-name cleanup.
2. Do not begin with template cleanup before shared runtime extraction.
3. Do not hide production complexity behind config changes.
4. Do not introduce general-purpose dumping grounds like `utils.py`.
5. Keep public module surfaces backward-compatible where they are already used.
6. Verify each structural phase with lint, typecheck, and relevant tests before
   proceeding.

## Practical order of execution

1. exclude `omniroute` and `wet` from the active WPS campaign;
2. implement shared `agent_mux` runtime primitives in `orchestra_agents`;
3. migrate templates and example agents to the shared runtime;
4. decompose `orchestra_thread` by operational role;
5. extract shared integration-test harness infrastructure;
6. clean up `telegram_mcp`;
7. run the final active-scope WPS sweep.

## Definition of success

The campaign is successful when all of the following are true:

- `omniroute` and `wet` no longer block active WPS progress reporting;
- duplicated complex runtime logic no longer exists across templates and
  example agents;
- `orchestra_thread` no longer depends on monolithic coordination modules;
- top integration tests use shared harness support instead of duplicating setup;
- remaining active WPS debt is small, local, and mechanically removable.
