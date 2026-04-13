# Front 3 — thread orchestration and Telegram edge layer

> Historical note: `src/telegram_mcp/**` belonged to this front only when the standalone `telegram-mcp` service existed. The service has since been removed; keep this document as historical context and do not treat `telegram-mcp` as active scope.

## Front mission

**Historical note:** legacy proxy routing has been replaced by `omniroute` + `wet`.

This front reduces active WPS debt in thread orchestration, MCP/thread HTTP
surfaces, persistent thread-store decomposition, and Telegram/event edge
services.

`src/core/omniroute/**` and `src/core/wet/**` are not part of this front.

## Front work scope

Core thread/orchestration modules:

- `src/core/orchestra_thread/**`

Telegram and edge modules:

- `src/core/telegram_events/**`
- `src/core/events_engine/**`
- `src/telegram_mcp/**` (archived historical scope; service removed)

Related test files owned by this front:

- `src/core/orchestra_thread/tests/**`
- `src/core/orchestra_thread/tests/fixtures/**`

## Current state

Current observed state of this front:

- `orchestra_thread` still carries concentrated production debt in client,
  handlers, MCP view/routing helpers, and store orchestration modules;
- large integration-style thread tests still hold substantial setup and await
  complexity;
- Telegram-side modules are smaller, but they still contribute edge-case WPS in
  config, listener, and bridge handling.

## System solution concept

The system solution for this front is to split the thread system by operational
responsibility:

1. storage concerns separate from handler concerns;
2. MCP tool families separate from route wiring and HTTP translation;
3. thread orchestration tests reuse extracted fixtures instead of embedding full
   scenario plumbing in each file;
4. Telegram and event bridges stay small edge adapters rather than accumulating
   orchestration policy.

## Implementation shape

This front should prefer these transformations:

- decompose thread store/query/notification behavior by responsibility;
- split HTTP and MCP surfaces by route/tool family;
- extract thread test harness fixtures for repeated setup/polling/assertion
  flows;
- keep Telegram/event modules thin and explicitly scoped.

This front must not:

- modify lifecycle platform ownership files from Front 2;
- refactor shared `agent_mux` runtime/template internals from Front 1;
- pull `omniroute` or `wet` into active work or use them as a dependency blocker.

## Completion signal

This front is complete when thread orchestration, its owned tests, and the
Telegram/event edge files are WPS-clean on their owned files and the remaining
debt is no longer concentrated in broad orchestration modules or scenario-heavy
thread tests.
