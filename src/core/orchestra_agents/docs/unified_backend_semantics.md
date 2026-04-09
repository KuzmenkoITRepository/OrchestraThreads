# Unified Backend Semantics

**Status:** Canonical contract
**Applies to:** sgr, agent_mux, opencode backends
**Last updated:** 2026-04-08

This document defines the authoritative contract for agent backend behavior in OrchestraThreads. All three backends (sgr, agent_mux, opencode) must implement the invariant semantics defined here. Capability-gated semantics are optional and backend-specific.

## Backend-Invariant Semantics

These semantics must be identical across all backends.

### `/event` — Event Delivery

**Purpose:** Deliver one or more events to the agent for processing.

**Request shape:**
```python
EventDelivery(
    delivery_id: str,           # Platform-generated unique delivery identifier
    events: list[AgentEvent],   # One or more events to process
    raw_payload: dict           # Original JSON payload
)
```

**Response shape:**
```python
EventDeliveryResult(
    accepted: bool,             # True if delivery was accepted
    accepted_events: list[str], # List of accepted event_id values
    delivery_id: str,           # Echo of request delivery_id
    duplicate: bool,            # True if delivery_id was already processed
    details: str | None         # Optional human-readable message
)
```

**Behavior:**
- Backend must accept the delivery and return acknowledgement synchronously
- Backend may process events asynchronously after acknowledgement
- Backend must track `delivery_id` to detect duplicate deliveries
- On duplicate delivery (same `delivery_id` seen before), backend must:
  - Return `accepted=False, duplicate=True`
  - Not re-process the events
  - Return the original `accepted_events` list if available
- Backend must process events in the order they appear in the `events` list
- Backend must not assume events belong to the same thread
- Backend must not assume events are contiguous in sequence_no

**Idempotency guarantee:** Repeated delivery of the same `delivery_id` must be safe and must not cause duplicate processing.

**Retry semantics:** Platform may retry failed deliveries with the same `delivery_id`. Backend must handle this via duplicate detection.

### `/stop` — Stop Active Work

**Purpose:** Stop active work and wait for new events.

**Request shape:**
```python
StopRequest(
    reason: str,                # Human-readable stop reason
    thread_id: str | None,      # Optional: stop only work for this thread
    parent_thread_id: str | None, # Optional: stop work for this parent thread
    raw_payload: dict           # Original JSON payload
)
```

**Response shape:**
```python
{
    "success": bool,            # True if stop was processed
    "message": str              # Human-readable result message
}
```

**Behavior:**
- Backend must stop active work (cancel in-flight LLM calls, abort processing)
- Backend must wait for new `/event` delivery after stop
- Backend must not exit or restart the agent process
- Backend must return success response synchronously
- If `thread_id` is provided and backend supports thread filtering:
  - Stop only work related to that thread
  - Continue processing other threads
- If `thread_id` is provided and backend does NOT support thread filtering:
  - Stop all work (thread filtering is a capability-gated feature)

**Capability note:** Thread-filtered stop is optional. See Capability-Gated Semantics.

### `/clear_context` — Reset Context

**Purpose:** Rotate context generation and reset delivery state.

**Request shape:**
```python
ClearContextRequest(
    requested_by: str,          # Agent or user requesting the reset
    raw_payload: dict           # Original JSON payload
)
```

**Response shape:**
```python
{
    "success": bool,            # True if context was cleared
    "message": str,             # Human-readable result message
    "context_generation": int   # New context generation number
}
```

**Behavior:**
- Backend must increment internal context generation counter
- Backend must reset delivery tracking state (clear seen delivery_ids)
- Backend must not exit or restart the agent process
- Backend must return new context generation number in response
- Backend must preserve agent configuration and manifest data

**Platform-owned field: `routing_key`**

The platform may include a `routing_key` field in the raw_payload. This is a platform-owned request field with backend-specific implementation:

- **SGR backend:** Implements full session reset via `reset_session(routing_key)`
- **agent_mux backend:** Accepts field but performs no-op (no session concept)
- **opencode backend:** Accepts field but performs no-op (no session concept)

Backends that don't implement session routing must accept and ignore `routing_key` without error.

### `/last_status` — Status Snapshot

**Purpose:** Return current agent status for observability.

**Response shape (minimum required fields):**
```python
{
    "agent_slug": str,          # Agent identifier
    "backend_type": str,        # Backend name (sgr, agent_mux, opencode)
    "context_generation": int,  # Current context generation
    "last_event_id": str | None,# Most recent processed event_id
    "last_delivery_id": str | None, # Most recent processed delivery_id
    "status": str               # Human-readable status string
}
```

**Behavior:**
- Backend must return status synchronously
- Backend may include additional backend-specific fields
- Backend must not block or perform expensive operations
- Status must reflect current state at time of request

### `/healthz` — Health Check

**Purpose:** Report agent readiness for event delivery.

**Response shape:**
```python
{
    "status": str,              # "healthy" or "unhealthy"
    "agent_slug": str,          # Agent identifier
    "backend_type": str         # Backend name
}
```

**Behavior:**
- Backend must return health status synchronously
- Backend must return HTTP 200 if healthy, 503 if unhealthy
- Backend must report unhealthy if not ready to accept events
- Backend must not block or perform expensive operations

### Startup — Lifecycle Hook

**Purpose:** Initialize backend and signal readiness.

**Behavior:**
- Backend must implement `on_start()` lifecycle hook
- Backend must complete initialization before accepting events
- Backend must signal readiness via `/healthz` endpoint
- Backend must load agent manifest and system prompt
- Backend must initialize MCP servers if configured
- Backend must not accept events until fully initialized

### Shutdown — Lifecycle Hook

**Purpose:** Clean up resources and stop gracefully.

**Behavior:**
- Backend must implement `on_shutdown()` lifecycle hook
- Backend must stop accepting new events
- Backend must complete or cancel in-flight work
- Backend must close MCP server connections
- Backend must release resources (file handles, network connections)
- Backend must exit cleanly within reasonable timeout (30s recommended)

### MCP Lifecycle

**Purpose:** Expose MCP tools to agent runtime.

**Behavior:**
- Platform provides MCP server configurations via manifest
- Backend must start MCP servers during `on_start()`
- Backend must expose MCP tools to agent execution context
- Backend must normalize MCP tool errors to standard format
- Backend must close MCP servers during `on_shutdown()`
- Backend must handle MCP server failures gracefully (log and continue)

**Error normalization:**
- MCP tool errors must be returned as structured error objects
- Backend must not crash on MCP tool failure
- Backend must include tool name and error message in normalized error

## Capability-Gated Semantics

These semantics are present only if the backend supports the capability.

### Session/Routing Key Support

**Capability:** Backend supports session-scoped context and routing.

**Supported by:** sgr
**Not supported by:** agent_mux, opencode

**Behavior (if supported):**
- Backend may implement `reset_session(routing_key)` method
- Backend may maintain separate context per routing_key
- Backend may route events to different sessions based on routing_key
- Platform may include `routing_key` in `/clear_context` raw_payload

**Behavior (if not supported):**
- Backend must accept `routing_key` field without error
- Backend must perform standard context clear (ignore routing_key)
- Backend must not crash or return error on routing_key presence

### Tool Filtering per MCP Server

**Capability:** Backend supports filtering which tools are enabled per MCP server.

**Supported by:** agent_mux
**Not supported by:** sgr, opencode

**Behavior (if supported):**
- Backend may read `enabled_tools` list from MCP server config
- Backend may expose only listed tools to agent execution context
- Backend may hide or disable tools not in `enabled_tools` list

**Behavior (if not supported):**
- Backend must expose all tools from all configured MCP servers
- Backend must ignore `enabled_tools` field if present in config

### Thread-Filtered Stop

**Capability:** Backend supports stopping work for specific thread only.

**Supported by:** agent_mux, opencode
**Not supported by:** sgr

**Behavior (if supported):**
- Backend must stop only work related to `thread_id` in StopRequest
- Backend must continue processing events for other threads
- Backend must track active work per thread

**Behavior (if not supported):**
- Backend must stop all active work regardless of `thread_id`
- Backend must accept `thread_id` field without error

## Backend-Internal Semantics

These semantics are explicitly NOT unified. Each backend may implement differently.

**Not part of the contract:**
- Execution model (in-process vs subprocess vs HTTP-wrapped)
- LLM routing details (OmniRoute vs direct API vs HTTP proxy)
- State persistence format (memory vs disk vs database)
- Queue/process management (single process vs worker pool)
- Internal session/context storage format
- Model selection and configuration
- Prompt construction and message history management
- Tool call execution strategy
- Error recovery and retry logic (internal to backend)

Backends are free to implement these details as needed for their execution model.

## Adapter Boundary

All backends must implement this adapter interface:

```python
class BaseAgentBackend(ABC):
    """Base adapter interface for agent backends."""

    # Lifecycle
    async def on_start(self) -> None:
        """Initialize backend and signal readiness."""

    async def on_shutdown(self) -> None:
        """Clean up resources and stop gracefully."""

    # Event processing
    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        """Process event delivery and return acknowledgement."""

    # Control
    async def stop(self, request: StopRequest) -> dict:
        """Stop active work and wait for new events."""

    async def clear_context(self, request: ClearContextRequest) -> dict:
        """Rotate context generation and reset delivery state."""

    # Observability
    async def last_status(self) -> dict:
        """Return current agent status snapshot."""

    async def health(self) -> dict:
        """Return health check status."""

    # Optional: Session support (SGR only)
    async def reset_session(self, routing_key: str) -> dict:
        """Reset session-specific context (capability-gated)."""
```

Backends that don't support optional methods must raise `NotImplementedError` or return error response.

## Swap Promise and Constraints

**What is guaranteed:**
- Backend switching is **restart-based with clean-state** semantics
- Agent manifest can specify `backend_type: sgr | agent_mux | opencode`
- Switching backend requires agent restart (no runtime hot-switching)
- All backends implement the invariant semantics defined above
- All backends expose the same HTTP endpoints (`/event`, `/stop`, `/clear_context`, `/last_status`, `/healthz`)

**What is NOT guaranteed:**
- Identical model outputs across backends
- Identical latency or performance characteristics
- State migration between backends (context is lost on switch)
- Preservation of backend-specific capabilities (session routing, tool filtering)

**Capability subset limitation:**
- If agent requires SGR-specific session routing, switching to opencode will lose that capability
- If agent requires agent_mux tool filtering, switching to sgr will expose all tools
- Agents should be designed for the **shared capability subset** if backend portability is required

**Clean state on switch:**
- Context generation resets to 0
- Delivery tracking state is cleared
- Session state (if any) is lost
- MCP servers are reinitialized
- Agent starts fresh with no memory of previous backend

## Structural Boundaries

**Shared platform behavior:**
- Lives under `src/core/orchestra_agents/runtime/`
- Includes: `app.py` (HTTP wrapper), `contracts.py` (request/response types), `backend.py` (base adapter), `bootstrap.py` (shared startup logic)
- Owned by platform, not by any specific backend

**Backend-specific behavior:**
- Lives under `src/core/orchestra_agents/backends/{sgr,agent_mux,opencode}/`
- Each backend is an **equal-status adapter**
- No backend has privileged ownership of shared platform logic

**Agent_mux internal details:**
- Queue/dispatch/state internals live under `src/core/orchestra_agents/backends/agent_mux/internal/`
- These are implementation details, not part of the platform contract
- Other backends must not depend on agent_mux internals

**Forbidden structure:**
- No top-level `src/core/orchestra_agents/agent_mux_runtime/` in final structure
- Agent_mux is an adapter, not the source of truth for platform behavior
- Shared bootstrap logic must live in `runtime/`, not in `agent_mux_runtime/`

## Versioning and Evolution

**Contract stability:**
- This document defines the v1 contract
- Breaking changes require new contract version
- Backends must declare which contract version they implement

**Adding new capabilities:**
- New capabilities must be capability-gated (optional)
- Backends that don't support new capability must accept and ignore related fields
- Platform must not require new capabilities for existing agents

**Deprecating endpoints:**
- Deprecated endpoints must remain functional for at least one major version
- Deprecation must be announced in this document with timeline
- Backends must log warnings when deprecated endpoints are used

## Implementation Checklist

When implementing a new backend or updating an existing one:

- [ ] Implement all invariant endpoints (`/event`, `/stop`, `/clear_context`, `/last_status`, `/healthz`)
- [ ] Implement `on_start()` and `on_shutdown()` lifecycle hooks
- [ ] Implement duplicate delivery detection via `delivery_id` tracking
- [ ] Implement context generation rotation on `/clear_context`
- [ ] Accept and ignore `routing_key` if session support not implemented
- [ ] Accept and ignore `thread_id` in `/stop` if thread filtering not implemented
- [ ] Return all required fields in `/last_status` response
- [ ] Return correct HTTP status codes (200 for healthy, 503 for unhealthy)
- [ ] Initialize MCP servers during `on_start()`
- [ ] Close MCP servers during `on_shutdown()`
- [ ] Normalize MCP tool errors to standard format
- [ ] Document any capability-gated features in backend-specific docs
- [ ] Test backend swap by switching manifest `backend_type` and restarting agent
