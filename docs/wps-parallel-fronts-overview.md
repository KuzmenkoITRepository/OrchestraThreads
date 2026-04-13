# WPS parallel execution fronts — common contract

> Historical note: this front split predates the removal of the standalone `telegram-mcp` service. Any `telegram_mcp` mentions below are archived references and should not be treated as active scope.

**Historical note:** legacy proxy routing has been replaced by `omniroute` + `wet`.

## Purpose

This document defines the shared execution model for the active WPS remediation
campaign. It replaces any earlier decomposition that treated `src/core/omniroute/`
and `src/core/wet/` as active workstreams.

`src/core/omniroute/` and `src/core/wet/` are **explicitly excluded** from all active fronts and are
also excluded from the active WPS check configuration.

## Active scope

The active remediation scope is limited to these areas:

- `src/core/orchestra_agents/**` except `src/core/omniroute/**` and `src/core/wet/**`
- `src/core/orchestra_thread/**`
- `src/core/events_engine/**`
- `src/core/telegram_events/**`
- `src/telegram_mcp/**` *(archived historical scope; service removed)*
- `agents/**`

## Explicitly excluded scope

The following area is not part of any execution front:

- `src/core/omniroute/**` and `src/core/wet/**`

Reasons for exclusion:

1. it is not part of the active WPS execution campaign;
2. including it distorts progress reporting for the maintained scope;
3. the current user instruction explicitly removes it from all work fronts.

## Current active state

At the time of this split:

- active WPS campaign excludes `src/core/omniroute/**` and `src/core/wet/**` in `setup.cfg`;
- the `agent_mux` shared runtime/parity slice has already been cleaned and
  verified locally;
- the repository still carries substantial active WPS debt in
  `orchestra_agents`, `orchestra_thread`, `agents/sgr`, and test harnesses;
- the front split must avoid shared file ownership and avoid cross-front API
  churn.

## Front decomposition rules

Each front must satisfy all of the following:

1. a file belongs to exactly one front;
2. each front owns both its production files and its directly related tests;
3. no front may move work into `omniroute` or `wet` or wait on their changes;
4. cross-front compatibility changes must be additive and backward-compatible;
5. lint reduction must come from responsibility reduction, not wrapper churn.

## Three active fronts

### Front 1 — agent runtime, template, and example-agent execution layer

Owns the shared `agent_mux` runtime, template runtime, example runtime adapters,
and the tests that validate those paths.

### Front 2 — agent lifecycle, manifest, registry, and platform contract layer

Owns the non-thread service platform inside `orchestra_agents`: manifest
parsing, registry behavior, runtime contract, Docker driver, lifecycle routes,
and the tests that validate those concerns.

### Front 3 — thread orchestration and Telegram edge layer

Owns `orchestra_thread`, related MCP and HTTP surfaces, plus Telegram and event
bridge edge services and their test harnesses.

## Coordination contract

The fronts are expected to run fully in parallel under these constraints:

- Front 1 must not change lifecycle API contracts owned by Front 2.
- Front 2 must not refactor `agent_mux` shared runtime internals owned by Front 1.
- Front 3 must not depend on `omniroute` or `wet` cleanup and must not edit `orchestra_agents`
  lifecycle or template ownership files.

Allowed cross-front behavior:

- read-only inspection of another front's public interface;
- additive compatibility preservation;
- coordination on test breakages caused by public contract changes.

Forbidden cross-front behavior:

- parallel edits to the same file;
- moving unresolved complexity into another front's module;
- reintroducing `omniroute` or `wet` into active scope.

## Verification standard for every front

Every front completes only when all of the following are true for its owned
files:

1. `ruff check` passes;
2. `flake8 --select=WPS` passes for the owned files;
3. relevant tests pass;
4. the change leaves no new diagnostics in the owned modules;
5. `omniroute` and `wet` remain excluded from both scope and progress reporting.

## Deliverables

This common document is paired with:

- `docs/wps-front-1-agent-runtime-template.md`
- `docs/wps-front-2-agent-lifecycle-platform.md`
- `docs/wps-front-3-thread-telegram-edge.md`

Those documents define the exact file ownership, current state, and system
solution concept for each front.
