# Agent Mux Template Implementation Plan

## Purpose

This directory is reserved for a future `agent_mux` template under
`core.orchestra_agents`.

The goal is to introduce a manifest-driven agent template that uses
`agent-mux` as an execution substrate while preserving the repository's core
service split:

- `orchestra_thread` owns durable `thread_id`, events, delivery, retries,
  inactivity, and status transitions.
- `orchestra_agents` owns manifest loading, template scaffolding, and runtime
  lifecycle.
- `omniroute` + `wet` own model/account routing and OpenAI/Codex-compatible HTTP
  access.

`agent-mux` must remain a worker runtime layer, not the owner of thread
semantics or agent lifecycle.

## Target Outcome

The finished template should let a manifest-defined agent:

- start behind the standard Orchestra HTTP runtime contract;
- register itself in `orchestra_thread`;
- accept delivered thread events through `/event`;
- build compact prompt context from `thread_compact` plus `thread_guide`;
- run a worker through `agent-mux`;
- send reply or status updates back into the same Orchestra thread;
- use `omniroute` + `wet` for Codex/OpenAI-compatible routing where applicable;
- support interruption, timeout recovery, and durable artifacts.

## Design Constraints

1. Do not move thread ownership into `agent-mux`.
2. Do not block the `/event` callback on a full worker run.
3. Keep compact-state-first prompting as the default path.
4. Keep the existing `orchestra_agents` runtime contract stable:
   - `GET /healthz`
   - `POST /event`
   - `POST /stop`
   - `GET /last_status`
   - `POST /clear_context`
5. Prefer additive changes:
   - add a new template;
   - add a new backend type;
   - do not break the current minimal template.

## Proposed Template Layout

```text
src/core/orchestra_agents/templates/agent_mux/
  IMPLEMENTATION_PLAN.md
  README.md
  manifest.yaml
  system_prompt.md
  .agent-mux/config.toml
  .agent-mux/prompts/worker.md
  .codex/config.toml
  agent_runtime/__init__.py
  agent_runtime/main.py
  agent_runtime/backend.py
  agent_runtime/dispatch.py
  agent_runtime/prompting.py
  agent_runtime/state.py
```

Generated agent directories should mirror that layout under `agents/<slug>/`.

## Runtime Model

### 1. HTTP Runtime Layer

The template continues to use `StandardAgentApplication` from
`core.orchestra_agents.runtime`.

`/event` must:

- validate the delivery payload;
- deduplicate delivered event ids;
- persist accepted work into a local queue/store;
- return success quickly.

It must not synchronously wait for `agent-mux` to finish, otherwise
`orchestra_thread` delivery retries will produce duplicates and spurious
failures.

### 2. Local Durable State

The template should keep a local runtime state root, for example:

```text
runtime_state/
  queue/
  artifacts/
  active_dispatches.json
  handled_events.json
```

Minimum tracked state:

- handled `event_id` set for dedup;
- `thread_id -> dispatch_id` mapping;
- dispatch terminal status;
- artifact directory path;
- last reply preview;
- last peer agent slug;
- last known `session_id` when available.

### 3. Worker Execution

Worker launches should use `agent-mux --stdin` with explicit JSON payload.

Preferred dispatch fields:

- `role`
- `variant`
- `engine`
- `model`
- `prompt`
- `system_prompt`
- `cwd`
- `artifact_dir`
- `timeout_sec`
- `full_access`
- `context_file`

The template should treat `agent-mux` as a supervised subprocess and parse its
single JSON result from stdout.

### 4. Prompt Construction

Prompting should stay compact by default.

Required inputs:

- latest actionable incoming event;
- `thread_compact` response;
- compact service guide from `thread_guide`;
- local system prompt;
- optional on-demand expansion only when compact state is insufficient.

Prompt composition should avoid replaying full event history into the worker.

### 5. Orchestra Thread Integration

Outgoing behavior should be normalized:

- normal answer -> `send_message`
- lifecycle update -> `send_notification`
- timeout with partial output -> short status update
- failure -> short review/error handoff, not raw internal logs

Reply sends must be idempotent via a stable `client_request_id`, ideally derived
from incoming `event_id` and action type.

### 6. Interruptions And Recovery

When a new interrupting event arrives for an active thread:

- if there is a live dispatch, use `agent-mux` steering first;
- if steering is not available, enqueue a resume/restart path;
- keep `thread_id` as the durable work identity and `dispatch_id` as local
  execution state only.

For `/stop`:

- abort the active dispatch for the target thread if one exists;
- clear local active mapping;
- return a normalized stop payload.

For timed-out dispatches:

- preserve artifact directory;
- mark runtime state as recoverable;
- optionally use `agent-mux --recover` on the next wake-up.

## omniroute + wet Integration

### Baseline Approach

The template should integrate `omniroute` + `wet` without pushing that concern into
`orchestra_thread`.

For Codex/OpenAI-compatible routing:

- generate a local Codex config file in `.codex/config.toml`;
- define a custom provider pointing at `omniroute` + `wet`;
- pass auth and route settings through environment.

### Compatibility Work

Current `omniroute` + `wet` routes already expose:

- `/v1/chat/completions`
- `/v1/codex/responses`
- `/codex/v1/codex/responses`
- `/minimax/v1/codex/responses`

For smoother Codex provider integration, add compatibility aliases if needed:

- `POST /v1/responses`
- optional route-specific aliases mirroring current policy paths

This should be implemented in `omniroute` + `wet`, not in the template.

## Manifest Shape

The template manifest should declare:

- standard agent working dir and HTTP endpoint;
- docker runtime command for `agent_runtime.main`;
- bind mount of the repo/workspace;
- env for `ORCHESTRA_THREADS_URL`, `OMNIROUTE_URL`, route policy, artifact
  root, and queue root;
- backend type `agent_mux`.

Example backend config target:

```yaml
backend:
  type: agent_mux
  config:
    role: worker
    variant: codex
    guide_view: compact
    threads_url: http://orchestra-threads:8788
    artifact_root: /workspace/runtime_state/artifacts
    queue_root: /workspace/runtime_state/queue
    auto_status_on_start: in_progress
    auto_status_on_timeout: review
    llm_route_policy: managed_auto
```

## Scaffold Changes

`core.orchestra_agents.scaffold` should be extended to support multiple
template roots.

Recommended change:

- add `--template agent|agent_mux`;
- default to the current `agent` template;
- resolve template root from `src/core/orchestra_agents/templates/<name>`.

This keeps the current behavior stable and makes `agent_mux` opt-in.

## Implementation Phases

### Phase 1. Template Skeleton

Create the new template directory and placeholder files:

- `README.md`
- `manifest.yaml`
- runtime entrypoint
- backend skeleton
- local config placeholders for `.agent-mux` and `.codex`

Deliverable:

- scaffold can materialize an `agent_mux` agent directory.

### Phase 2. Backend Adapter

Implement `AgentMuxBackend` with:

- thread-service registration and heartbeat;
- quick `/event` accept path;
- local event dedup;
- single-thread worker ownership;
- basic synchronous worker execution from queued jobs.

Deliverable:

- one delivered thread message can trigger one `agent-mux` worker and one reply.

### Phase 3. Compact Prompting

Implement prompt assembly from:

- incoming event;
- `thread_compact`;
- `thread_guide`;
- system prompt;
- optional compact wake-up summary generation.

Deliverable:

- no full thread replay required for normal tasks.

### Phase 4. Result Mapping

Translate `agent-mux` result payload into Orchestra actions:

- completed -> message reply
- completed with handoff-style output -> review status if configured
- timed_out -> partial status update
- failed -> short review/error notification

Deliverable:

- stable, observable mapping from dispatch result to thread state.

### Phase 5. Interrupt And Stop Handling

Implement:

- stop -> abort active dispatch;
- interrupting event -> steer redirect or queued recovery;
- context clear -> drop local per-thread execution memory.

Deliverable:

- runtime behaves correctly under repeated delivery and cancellation.

### Phase 6. omniroute + wet Compatibility

Implement and verify:

- Codex config generation;
- provider wiring through `omniroute` + `wet`;
- any `omniroute` or `wet` path aliases required for compatibility.

Deliverable:

- template works with managed proxy routing instead of direct provider calls.

### Phase 7. Docker E2E Validation

Add dockerized tests covering:

- agent start/stop lifecycle;
- event delivery and quick ack;
- compact-state prompt flow;
- timeout and recovery;
- omniroute/wet-backed execution path.

Deliverable:

- validation through the repository's canonical Docker test path.

## Test Plan

### Unit Tests

- scaffold resolves the new template root correctly;
- manifest validation accepts the `agent_mux` template output;
- backend deduplicates repeated `event_id`;
- backend does not emit duplicate replies on retried delivery;
- result mapping chooses the correct Orchestra action;
- stop and clear-context reset local runtime state.

### Integration Tests

- fake thread service + fake `agent-mux` subprocess;
- fake `omniroute` + `wet` route for Codex/OpenAI-compatible calls;
- interrupting event during active dispatch;
- timed-out dispatch with recoverable artifacts.

### Docker E2E

Run through:

```bash
docker compose --profile test run --rm test
```

## Risks

1. Blocking `/event` on worker completion will break delivery semantics.
2. Mapping `dispatch_id` too closely to `thread_id` will leak runtime concerns
   into service-level workflow.
3. Codex provider compatibility may require small `omniroute` + `wet` API aliases.
4. Steering behavior differs by engine, so the first usable version should focus
   on one primary path before broad multi-engine support.

## Recommended First Slice

Build the smallest production-worthy slice in this order:

1. scaffold support for `agent_mux`
2. template skeleton
3. backend queue + fast ack
4. single-engine `agent-mux` dispatch
5. compact thread fetch + reply send
6. unit tests

This gives a usable template quickly without committing the repo to premature
pipeline or multi-engine complexity.
