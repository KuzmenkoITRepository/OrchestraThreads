# Unified Manifest Schema Specification

**Version:** 1.0
**Status:** Draft
**Last Updated:** 2026-04-08

## Overview

This document defines the canonical manifest schema for Orchestra agent definitions. The unified schema separates author concerns (what the agent does) from platform concerns (how it runs), while preserving compatibility with the repository's current migration state.

**Key principle:** The outer manifest envelope is unified today (`slug`, `display_name`, `status`, `agent`, `backend`, optional `auto_start`, optional legacy `runtime`). Runtime derivation is the target direction, but explicit `runtime` blocks are still supported in current manifests and templates.

## Current Canonical Schema

Agent authors must follow the unified outer manifest shape. Backend-specific details live under `backend.config`. During the current migration phase, manifests may still include explicit `runtime` blocks, and the platform continues to accept them.

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

## Platform-Derived Runtime (Target Direction)

These fields are the intended platform-managed runtime surface. In the current repository state, they are not fully author-hidden yet: real manifests and templates may still set `runtime` explicitly, and the platform accepts that during migration.

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

The `backend.config` object is validated per `backend.type`, but current enforcement is migration-compatible rather than fully strict for every top-level key.

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
**Optional keys:** `temperature`, `max_tokens`, `timeout_seconds`, `react_to_inactive`, `max_reasoning_steps`, `max_direct_text_retries`, `mcp_servers`

**SGR `mcp_servers` shape:**

```yaml
mcp_servers:
  - name: string                  # Required. Logical MCP entry name
    module: string                # Required. Import path for the server module
    class: string                 # Required. MCP server class name
    schema_fn: string             # Optional. Function returning tool definitions
```

SGR supports inline Python MCP registration only. Subprocess-style MCP fields such as
`command`, `args`, `cwd`, `startup_timeout_sec`, `required`, `enabled`, `enabled_tools`,
and `env` belong to other backends and are invalid for `sgr_minimax` manifests.

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

## Current Validation Behavior

The platform validates manifests against the current parser and backend-specific compatibility rules. Some areas are strict today, while others remain permissive during migration.

### Top-Level Validation

- **Unknown top-level manifest fields:** Rejected. Only supported manifest fields such as `slug`, `display_name`, `status`, `auto_start`, `agent`, `backend`, and the current migration-era `runtime` block are accepted.
- **Missing required fields:** Rejected. Must have `slug`, `display_name`, `status`, `agent`, `backend`.
- **Type mismatches:** Enforced for the parsed manifest surface, but backend-config value typing is not yet universally strict across every backend-specific field.

### Backend Config Validation

- **Unknown `backend.type`:** Accepted during migration compatibility if `runtime.image` is provided. The parser logs a warning and preserves the custom backend type.
- **Unknown top-level `backend.config` keys:** Currently warned, not rejected, for known backends. The parser only hard-rejects unsupported fields inside backend-specific nested structures such as `backend.config.mcp_servers[*]`.
- **Missing required config keys:** Rejected per backend type.
- **Type mismatches in config:** Only partially enforced today. Current validation primarily checks required keys, allowed key sets, and selected nested structures rather than performing full type validation for every backend config value.

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
- Migration compatibility still allows unknown backend types when `runtime.image` is present; those cases log warnings rather than hard-failing.

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
4. Validate the final resolved manifest against the current parser and backend-specific compatibility rules.

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

### Automated Migration Tool (Current Utility + Future Bulk Migration)

The repository currently contains a single-manifest migration utility at `scripts/migrate_agent_manifest.py`. A bulk migration flow for all manifests is still planned.

Current utility behavior:

1. Read one manifest file.
2. Parse YAML.
3. Migrate legacy/runtime-managed fields into the unified outer shape.
4. Preserve backend-specific `backend.config`.
5. Emit the migrated manifest to stdout or an output path.

Planned bulk migration behavior:

1. Scan all `agents/*/manifest.yaml` files.
2. Run the single-manifest migration per file.
3. Generate a migration report with validation failures and diffs.

### Manual Migration Steps

For custom manifests outside `agents/`:

1. Identify `backend.type` from existing `runtime.image` or `runtime.command`.
2. Extract backend-specific config from `runtime.env` and move to `backend.config`.
3. Remove entire `runtime` block.
4. Validate by parsing the manifest with the current `orchestra-agents` manifest loader or via the migration utility plus parser checks.

### Validation Workflow (Current)

There is no documented `orchestra-agents` HTTP validation endpoint in the current repository. The supported validation path today is:

1. Parse the manifest through `AgentManifest.from_yaml_text(...)` / `AgentManifest.from_file(...)`.
2. For legacy manifests, optionally run `scripts/migrate_agent_manifest.py` first and parse the migrated output.
3. Treat parser errors as validation failures and parser warnings as migration-compatibility signals that still need operator review.

## Full Resolved Spec Example

**Author may write today (minimal future-style):**

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

## Current-State Notes

- The unified outer manifest contract is current and enforced.
- `backend.config` is validated per backend type, but current enforcement is intentionally migration-compatible rather than fully strict for every field.
- `backend.config.mcp_servers` is backend-specific today:
  - `sgr_minimax` uses inline Python MCP entries (`name`, `module`, `class`, optional `schema_fn`)
  - `agent_mux` uses subprocess MCP entries (`name`, `command`, optional `args`, `cwd`, `startup_timeout_sec`, `required`, `enabled`, `enabled_tools`, `env`)
  - `opencode_omo` uses subprocess/local-server MCP entries (`name`, `command`, optional `args`, `env`)
- Explicit `runtime` blocks are still present in real manifests and templates and remain valid during migration.
- Unknown backend types are still accepted when enough runtime information is supplied for compatibility, and they generate warnings rather than immediate rejection.
- Unknown top-level backend-config keys currently generate warnings for known backends; unsupported nested MCP entry fields are rejected.

## Implementation Notes

### Manifest Dataclass Shape

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

### Current Validation Entry Points

```python
AgentManifest.from_yaml_text(yaml_text: str) -> AgentManifest
AgentManifest.from_file(path: Path) -> AgentManifest
```

Current validation is performed during parsing. Invalid manifests raise `ManifestValidationError`; migration-compatible cases such as unknown backend types with explicit `runtime.image` may still parse successfully while logging warnings.

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
- **Migration Tool:** `scripts/migrate_agent_manifest.py` (current single-manifest utility)

## Changelog

**2026-04-08:** Initial draft. Defined target schema, platform derivation rules, backend-specific config schemas, current migration-compatible validation behavior, actual parser-based validation entry points, and migration path.
