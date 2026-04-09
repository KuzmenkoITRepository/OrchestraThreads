# Unified Manifest Schema Specification

**Version:** 1.0
**Status:** Draft
**Last Updated:** 2026-04-08

## Overview

This document defines the canonical manifest schema for Orchestra agent definitions. The unified schema separates author concerns (what the agent does) from platform concerns (how it runs).

**Key principle:** Authors declare intent via `backend.type` and `backend.config`. The platform derives runtime configuration automatically.

## Target Author Schema

Agent authors write minimal manifests containing only business logic and backend selection. The platform handles Docker images, entrypoints, environment variables, and Python paths.

### Core Fields

```yaml
slug: string                    # Required. Agent identifier (lowercase, hyphens)
display_name: string            # Required. Human-readable name
status: active | inactive       # Required. Deployment status
auto_start: boolean             # Optional. Default: false

agent:
  working_dir: string           # Required. Container working directory
  http_endpoint: string         # Required. Template: http://{container_name}:8080
  system_prompt_file: string    # Optional. Path relative to manifest directory
  allowed_peer_agent_slugs:     # Optional. List of peer agent slugs
    - string

backend:
  type: string                  # Required. One of: sgr_minimax, agent_mux, opencode_omo
  config: object                # Required. Backend-specific configuration (see below)
```

### Minimal Example (SGR Backend)

```yaml
slug: my-sgr-agent
display_name: My SGR Agent
status: active
auto_start: false

agent:
  working_dir: /workspace/agents/my-sgr-agent
  http_endpoint: http://{container_name}:8080
  system_prompt_file: system_prompt.md

backend:
  type: sgr_minimax
  config:
    route_policy: codex_only
    model: cx/gpt-5.4-mini
    temperature: 0.7
    max_tokens: 4096
```

## Platform-Derived Fields

These fields are **platform-derived** — computed by the platform based on `backend.type`. Authors should NOT set them in unified manifests.

### Runtime Configuration (Platform-Managed)

```yaml
runtime:
  driver: string                # Always "docker" (platform default)
  image: string                 # Selected by platform per backend.type
  entrypoint: list[string]      # Set by platform per backend.type
  command: list[string]         # Set by platform per backend.type
  mounts: list[object]          # Platform provides standard mounts
  env: dict[string, string]     # Platform provides base env per backend
  env_passthrough: list[string] # Platform provides base passthrough per backend
```

### Platform Derivation Rules

| Backend Type | Runtime Image | Command | Base PYTHONPATH |
|--------------|---------------|---------|-----------------|
| `sgr_minimax` | `orchestra-threads:local` | `[python, -m, core.orchestra_agents.backends.sgr.main]` | `/workspace/src:/workspace` |
| `agent_mux` | `orchestra-agent-mux-runtime:latest` | `[python, -m, core.orchestra_agents.backends.agent_mux.main]` | `/workspace/src` |
| `opencode_omo` | `orchestra-opencode-runtime:latest` | `[python, -m, core.orchestra_agents.backends.opencode.main]` | `/workspace/src` |

### Platform-Provided Environment Variables

**All backends receive:**
```yaml
OMNIROUTE_URL: http://orchestra-omniroute:20128
AGENT_SLUG: {slug}
WORKING_DIR: {agent.working_dir}
```

**Backend-specific additions:**

**agent_mux:**
```yaml
AGENT_MUX_BINARY: agent-mux
```

**opencode_omo:**
```yaml
OPENCODE_RUNTIME_STATE_ROOT: /tmp/opencode-runtime/{slug}
```

### Platform-Provided Mounts

**All backends receive:**
```yaml
- type: bind
  source: ./src
  target: /workspace/src
  read_only: true

- type: bind
  source: ./agents/{slug}
  target: /workspace/agents/{slug}
  read_only: true
```

**agent_mux additional mounts:**
```yaml
- type: bind
  source: ./agents/{slug}/runtime_state
  target: /workspace/agents/{slug}/runtime_state
  read_only: false
```

## Backend-Specific Config Schemas

The `backend.config` object is validated strictly per `backend.type`. Unknown keys are rejected.

### sgr_minimax

```yaml
backend:
  type: sgr_minimax
  config:
    route_policy: string              # Required. LLM routing policy
    model: string                     # Required. Model identifier
    temperature: float                # Optional. Default: 0.7
    max_tokens: integer               # Optional. Default: 4096
    timeout_seconds: integer          # Optional. Default: 300
    react_to_inactive: boolean        # Optional. Default: false
    max_reasoning_steps: integer      # Optional. Default: 10
    max_direct_text_retries: integer  # Optional. Default: 3
```

**Required keys:** `route_policy`, `model`
**Optional keys:** `temperature`, `max_tokens`, `timeout_seconds`, `react_to_inactive`, `max_reasoning_steps`, `max_direct_text_retries`

### agent_mux

```yaml
backend:
  type: agent_mux
  config:
    role: string                      # Required. One of: worker, coordinator
    artifact_root: string             # Optional. Default: /tmp/artifacts
    llm_route_policy: string          # Required. LLM routing policy
    model: string                     # Required. Model identifier
    timeout_seconds: integer          # Optional. Default: 300
    require_tool_call_for_response: boolean  # Optional. Default: false
    mcp_servers:                      # Optional. List of MCP server configs
      - name: string                  # Required. Server identifier
        command: string               # Required. Executable path
        args: list[string]            # Optional. Command arguments
        cwd: string                   # Optional. Working directory
        startup_timeout_sec: integer  # Optional. Default: 30
        required: boolean             # Optional. Default: false
        enabled: boolean              # Optional. Default: true
        enabled_tools: list[string]   # Optional. Tool whitelist
        env: dict[string, string]     # Optional. Server-specific env vars
```

**Required keys:** `role`, `llm_route_policy`, `model`
**Optional keys:** `artifact_root`, `timeout_seconds`, `require_tool_call_for_response`, `mcp_servers`

### opencode_omo

```yaml
backend:
  type: opencode_omo
  config:
    model: string                     # Required. Model identifier
    opencode_serve_port: integer      # Optional. Default: 4096
    dispatch_timeout_seconds: integer # Optional. Default: 300
    startup_timeout_seconds: integer  # Optional. Default: 60
    mcp_servers:                      # Optional. List of MCP server configs
      - name: string                  # Required. Server identifier
        command: string               # Required. Executable path
        args: list[string]            # Optional. Command arguments
        env: dict[string, string]     # Optional. Server-specific env vars
```

**Required keys:** `model`
**Optional keys:** `opencode_serve_port`, `dispatch_timeout_seconds`, `startup_timeout_seconds`, `mcp_servers`

## Strict Validation Rules

The platform validates manifests in strict mode by default.

### Top-Level Validation

- **Unknown fields:** Rejected. Only `slug`, `display_name`, `status`, `auto_start`, `agent`, `backend`, `runtime` (deprecated) allowed.
- **Missing required fields:** Rejected. Must have `slug`, `display_name`, `status`, `agent`, `backend`.
- **Type mismatches:** Rejected. All fields must match declared types.

### Backend Config Validation

- **Unknown `backend.type`:** Rejected. Must be one of `sgr_minimax`, `agent_mux`, `opencode_omo`.
- **Unknown `backend.config` keys:** Rejected per backend type. Only documented keys allowed.
- **Missing required config keys:** Rejected per backend type.
- **Type mismatches in config:** Rejected. All config values must match backend schema.

### Agent Config Validation

- **`http_endpoint` template:** Must contain `{container_name}` placeholder.
- **`system_prompt_file` path:** Must be relative (no leading `/`).
- **`allowed_peer_agent_slugs`:** Each slug must reference an existing agent.

## Backward Compatibility During Migration

Existing manifests with explicit `runtime.*` fields continue to work during the migration period. The platform normalizes legacy manifests automatically.

### Legacy Manifest Handling

**Phase 1: Acceptance (Current)**
- Manifests with explicit `runtime` blocks are accepted.
- Explicit runtime fields override platform defaults.
- No warnings logged.

**Phase 2: Deprecation (Q2 2026)**
- Manifests with explicit `runtime` blocks trigger deprecation warnings in logs.
- Functionality unchanged.
- Warning message: `"Agent {slug}: explicit runtime.* fields are deprecated. Remove runtime block and rely on platform defaults per backend.type."`

**Phase 3: Migration (Q3 2026)**
- Automated migration tool converts all manifests to unified schema.
- Explicit `runtime` blocks removed.
- Backend-specific config extracted and validated.

**Phase 4: Enforcement (Q4 2026)**
- Explicit `runtime` blocks rejected.
- Only unified schema accepted.

### Normalization Algorithm

When loading a legacy manifest:

1. Parse manifest YAML.
2. If `runtime` block present:
   - Log deprecation warning (Phase 2+).
   - Merge explicit runtime fields with platform defaults (explicit wins).
   - Validate merged runtime config.
3. If `runtime` block absent:
   - Derive full runtime config from `backend.type` using platform rules.
4. Validate final resolved manifest against strict schema.

### Field-by-Field Compatibility

| Field | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|-------|---------|---------|---------|---------|
| `runtime.driver` | Accepted, overrides platform | Accepted, warns | Removed by migration | Rejected |
| `runtime.image` | Accepted, overrides platform | Accepted, warns | Removed by migration | Rejected |
| `runtime.entrypoint` | Accepted, overrides platform | Accepted, warns | Removed by migration | Rejected |
| `runtime.command` | Accepted, overrides platform | Accepted, warns | Removed by migration | Rejected |
| `runtime.mounts` | Accepted, merged with platform | Accepted, warns | Removed by migration | Rejected |
| `runtime.env` | Accepted, merged with platform | Accepted, warns | Removed by migration | Rejected |
| `runtime.env_passthrough` | Accepted, merged with platform | Accepted, warns | Removed by migration | Rejected |

**Merge strategy for lists (mounts, env_passthrough):**
- Platform provides base list.
- Explicit manifest entries appended.
- Duplicates removed (explicit wins).

**Merge strategy for dicts (env):**
- Platform provides base dict.
- Explicit manifest entries override platform values.

## Migration Path

### Automated Migration Tool (Task 9)

The migration tool (`scripts/migrate_manifests.py`) will:

1. Scan all `agents/*/manifest.yaml` files.
2. For each manifest:
   - Parse YAML.
   - If `runtime` block present:
     - Extract backend-specific config from `runtime.env` and `runtime.command`.
     - Remove entire `runtime` block.
     - Validate `backend.config` against strict schema.
     - Write updated manifest.
   - If `runtime` block absent:
     - Skip (already unified).
3. Generate migration report:
   - Count of migrated manifests.
   - List of validation errors (if any).
   - Diff summary per manifest.

### Manual Migration Steps

For custom manifests outside `agents/`:

1. Identify `backend.type` from existing `runtime.image` or `runtime.command`.
2. Extract backend-specific config from `runtime.env` and move to `backend.config`.
3. Remove entire `runtime` block.
4. Validate against strict schema using `orchestra-agents` validation endpoint.

### Validation Endpoint

```bash
POST /api/v1/agents/validate-manifest
Content-Type: application/yaml

<manifest YAML>
```

**Response (success):**
```json
{
  "valid": true,
  "resolved_manifest": { ... }
}
```

**Response (failure):**
```json
{
  "valid": false,
  "errors": [
    "Unknown backend.config key: invalid_key",
    "Missing required field: backend.config.model"
  ]
}
```

## Full Resolved Spec Example

**Author writes (minimal):**

```yaml
slug: my-agent
display_name: My Agent
status: active

agent:
  working_dir: /workspace/agents/my-agent
  http_endpoint: http://{container_name}:8080
  system_prompt_file: system_prompt.md

backend:
  type: sgr_minimax
  config:
    route_policy: codex_only
    model: cx/gpt-5.4-mini
```

**Platform resolves internally:**

```yaml
slug: my-agent
display_name: My Agent
status: active
auto_start: false
manifest_path: /workspace/agents/my-agent/manifest.yaml

agent:
  working_dir: /workspace/agents/my-agent
  http_endpoint: http://my-agent:8080
  system_prompt_file: system_prompt.md
  allowed_peer_agent_slugs: []

backend:
  type: sgr_minimax
  config:
    route_policy: codex_only
    model: cx/gpt-5.4-mini
    temperature: 0.7
    max_tokens: 4096
    timeout_seconds: 300
    react_to_inactive: false
    max_reasoning_steps: 10
    max_direct_text_retries: 3

runtime:
  driver: docker
  image: orchestra-threads:local
  entrypoint: null
  command: [python, -m, core.orchestra_agents.backends.sgr.main]
  mounts:
    - type: bind
      source: ./src
      target: /workspace/src
      read_only: true
    - type: bind
      source: ./agents/my-agent
      target: /workspace/agents/my-agent
      read_only: true
  env:
    OMNIROUTE_URL: http://orchestra-omniroute:20128
    AGENT_SLUG: my-agent
    WORKING_DIR: /workspace/agents/my-agent
    PYTHONPATH: /workspace/src:/workspace
  env_passthrough:
    - VAULT_ADDR
    - VAULT_TOKEN
```

## Implementation Notes

### Dataclass Changes Required

**Current `AgentManifest` (manifest.py):**
```python
@dataclass
class AgentManifest:
    slug: str
    display_name: str
    status: str
    agent: AgentConfig
    runtime: RuntimeConfig
    backend: BackendConfig
    auto_start: bool = False
    manifest_path: str | None = None
```

**Target `AgentManifest` (unified schema):**
```python
@dataclass
class AgentManifest:
    slug: str
    display_name: str
    status: str
    agent: AgentConfig
    backend: BackendConfig
    auto_start: bool = False
    manifest_path: str | None = None
    runtime: RuntimeConfig | None = None  # Deprecated, for backward compat only
```

### Validation Function Signature

```python
def validate_manifest(
    manifest: AgentManifest,
    strict: bool = True,
) -> tuple[bool, list[str]]:
    """
    Validate manifest against unified schema.

    Args:
        manifest: Parsed manifest object
        strict: Reject unknown fields and deprecated runtime block

    Returns:
        (is_valid, error_messages)
    """
```

### Platform Derivation Function Signature

```python
def derive_runtime_config(
    backend_type: str,
    slug: str,
    working_dir: str,
) -> RuntimeConfig:
    """
    Derive full runtime config from backend type.

    Args:
        backend_type: One of sgr_minimax, agent_mux, opencode_omo
        slug: Agent slug for path substitution
        working_dir: Agent working directory

    Returns:
        Complete RuntimeConfig with platform defaults
    """
```

## References

- **Manifest Dataclasses:** `src/core/orchestra_agents/manifest.py`
- **Backend Adapters:** `src/core/orchestra_agents/backends/`
- **Runtime Contract:** `src/core/orchestra_agents/runtime/`
- **Example Manifests:** `agents/*/manifest.yaml`
- **Migration Tool:** `scripts/migrate_manifests.py` (planned)

## Changelog

**2026-04-08:** Initial draft. Defined target schema, platform derivation rules, backend-specific config schemas, strict validation rules, and migration path.
