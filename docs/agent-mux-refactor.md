# agent-mux refactor

## Problem

Current `agent_mux` runtime mixes two separate responsibilities:

- generic agent runtime concerns:
  - accept `POST /event`
  - deduplicate and queue deliveries
  - keep durable `context_id`
  - launch `agent-mux --stdin`
  - expose `health`, `last_status`, and `clear_context`
- thread-specific orchestration concerns:
  - require `thread_id` for actionable work
  - fetch `thread_compact`
  - infer peer agent from thread state
  - require `thread_send` / `thread_status`
  - treat OrchestraThreads MCP mutations as the only valid completion path

This makes the runtime itself thread-centric, while threads are supposed to remain external durable workflow semantics owned by `orchestra_threads`.

**Additionally**, `sgr` agent (and other agent templates) have thread-specific assumptions baked into their system prompts and backend logic, making them unable to handle non-thread events (e.g., Telegram messages, calendar events).

## Target State

`agent_mux` must become a generic event-driven runtime.

It must not:

- depend on `thread_id`
- depend on `chat_id`
- derive its execution model from `thread_compact`
- hardcode OrchestraThreads MCP as built-in runtime behavior
- require one specific tool family for successful completion

It must:

- generate and own `context_id` internally
- keep `context_id` stable across restarts
- rotate `context_id` only via `POST /clear_context`
- accept arbitrary event payloads through `POST /event`
- queue and deduplicate events durably
- expose generic active event context to optional tools
- allow MCP servers to be configured from runtime config instead of hardcoding them

## Final Boundary

### agent_mux runtime owns

- HTTP event intake
- local durable queue
- event deduplication by `event_id`
- context memory
- active dispatch lifecycle
- Codex/LLM dispatch execution
- generic status and health reporting

### external integrations own

- thread semantics
- Telegram semantics
- calendar semantics
- routing rules
- reply policies
- specific MCP server tool contracts

If an agent uses OrchestraThreads tools, that is a property of the agent configuration and prompt, not of the runtime core.

## Refactor Plan

### Phase 1: agent-mux runtime (generic event-driven core)

**Goal**: Make agent-mux runtime completely thread-agnostic while preserving ability to pass thread metadata through as opaque payload.

**Files to modify:**
- `src/core/orchestra_agents/templates/agent_mux/agent_runtime/backend.py`
- `src/core/orchestra_agents/templates/agent_mux/agent_runtime/prompting.py`

**Changes:**

1. **backend.py** - Already mostly generic, verify:
   - ✓ `_active_context_payload()` treats thread fields as optional metadata (lines 637-656)
   - ✓ Queue processing is FIFO via `claim_next_entry()` (line 433)
   - ✓ `_is_actionable_event()` is generic (line 519)
   - ✓ MCP servers come from config (line 541, `mcp_servers` parameter)
   - ✓ No hardcoded thread-specific completion checks
   - **Action**: Verify no hidden thread dependencies remain

2. **prompting.py** - Make thread fields clearly optional:
   - Thread fields in `_STANDARD_EVENT_KEYS` are already treated as optional
   - `build_compact_wakeup_block()` doesn't require thread fields
   - **Action**: Add comment clarifying thread fields are optional metadata

3. **state.py** - Already generic:
   - ✓ `context_id` management is runtime-owned
   - ✓ Queue is FIFO
   - **Action**: No changes needed

4. **dispatch.py** - Already supports config-driven MCP:
   - ✓ `write_runtime_codex_config()` accepts `mcp_servers` list
   - **Action**: No changes needed

### Phase 2: sgr agent (remove thread-centric assumptions)

**Goal**: Make sgr agent work with any event type, using thread MCP tools only when `thread_id` is present in event payload.

**Files to modify:**
- `agents/sgr/agent_runtime/backend.py`
- `agents/sgr/system_prompt.md`
- `agents/sgr/manifest.yaml`

**Changes:**

1. **backend.py** - Make thread integration conditional:
   - Remove mandatory `OrchestraThreadsClient` registration on startup
   - Remove mandatory `get_thread_compact` fetching
   - Remove peer inference from thread state
   - Make thread-specific behavior conditional: only fetch thread_compact if event contains `thread_id`
   - Keep thread MCP tools available via manifest config

2. **system_prompt.md** - Make thread tools conditional:
   ```markdown
   You are `sgr`, a proactive manifest-driven Orchestra agent.

   Use configured MCP tools for external actions, not direct assistant prose.

   Rules:

   - If operating in thread context (event contains `thread_id`):
     - Use `thread_send` for peer-facing messages
     - Use `thread_status` for status updates (`in_progress`, `review`, `done`, `closed`)
     - Call `thread_current` if thread state is unclear
     - Use `thread_expand` when compact state is insufficient
     - Use `thread_guide` for routing/lifecycle rules
   - For non-thread events:
     - Use appropriate MCP tools based on event type and available tools
     - Respond through configured channels (e.g., Telegram, calendar)
   - Keep messages concise, concrete, and operational
   - Do not mention internal implementation details (manifests, thread IDs, runtime state)
   - Do not rely on plain assistant text as the final result
   ```

3. **manifest.yaml** - Add explicit MCP server configuration:
   ```yaml
   backend:
     type: sgr_minimax
     config:
       # ... existing config ...
       mcp_servers:
         - name: orchestra_threads
           command: python
           args:
             - "-m"
             - "core.orchestra_thread.mcp_server"
           env:
             ORCHESTRA_THREADS_URL: "{ORCHESTRA_THREADS_URL}"
             PYTHONPATH: "{pythonpath}"
           cwd: "{agent_working_dir}"
           enabled: true
   ```

### Phase 3: secretary agent (same treatment)

**Files to modify:**
- `agents/secretary/system_prompt.md`
- `agents/secretary/manifest.yaml`

**Changes:**
- Same as sgr agent - make thread tools conditional, not mandatory
- Update system prompt with conditional thread tool usage
- Add explicit MCP server configuration to manifest

### Phase 4: Update documentation

**Files to modify:**
- `src/core/orchestra_agents/templates/agent_mux/README.md` (if exists)
- `src/core/orchestra_agents/docs/README.md`

**Changes:**
- Document that agent-mux runtime is event-agnostic
- Document MCP server configuration format
- Document how to create thread-aware vs thread-agnostic agents
- Provide examples of both patterns

## Implementation Order

1. **Phase 1** (agent-mux runtime) - Verify generic behavior, add clarifying comments
2. **Phase 2** (sgr agent) - Full refactor to conditional thread usage
3. **Phase 3** (secretary agent) - Apply same pattern
4. **Phase 4** (documentation) - Update all docs

## Expected Result After Refactor

- `agent_mux` runtime is completely thread-agnostic
- `agent_mux` can process events without `thread_id`
- Thread fields are passed through as optional metadata when present
- `sgr` and `secretary` agents work with any event type
- Thread MCP tools are used only when event contains `thread_id`
- OrchestraThreads integration remains fully functional for thread-based workflows
- New event sources (Telegram, calendar) can be integrated without modifying runtime
- `context_id` is the only runtime-native durable execution identity

## Verification Requirements

Before considering the task complete:

1. **Unit tests**:
   - Run Docker test suite: `docker compose --profile test run --rm test`
   - All existing tests must pass

2. **Manual smoke tests**:
   - Start agent-mux runtime
   - Send `POST /event` without `thread_id` - should process successfully
   - Send `POST /event` with `thread_id` - should use thread MCP tools
   - Verify `GET /last_status` shows correct state
   - Verify `POST /clear_context` rotates `context_id`
   - Verify `context_id` persists across restarts

3. **Integration tests**:
   - Test sgr agent with thread event - should use thread_send/thread_status
   - Test sgr agent with non-thread event - should work without thread tools
   - Verify no errors in logs about missing thread_id

## Notes

- **Backward compatibility**: Thread-based workflows must continue working without changes
- **Boundary enforcement**: Only `orchestra_threads` service knows about thread semantics
- **Agent flexibility**: Agents can work with threads, Telegram, calendar, or any future event source
- **Configuration clarity**: MCP servers are explicitly declared in manifests, not implicit
