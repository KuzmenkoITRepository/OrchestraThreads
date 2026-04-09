# Backend Migration & Rollout Policy

## Overview

This document defines the phased rollout order, rollback procedures, backward
compatibility rules, and temporary shim lifecycle for the backend unification
refactor. All three backends — `sgr_minimax`, `agent_mux`, and `opencode_omo` —
are migrated onto equal-status adapters under a single shared runtime kernel.

## Core Principles

1. **Restart-based switching only.** Backend switching requires a clean-state
   container restart. No in-flight or persisted backend-native state is carried
   across a backend switch.
2. **No state migration.** Each backend restart begins with a fresh runtime
   state derived from the manifest and platform defaults.
3. **Incremental rollout.** Each migration phase is independently deployable and
   independently reversible.
4. **Automated verification.** Every phase has runnable acceptance commands; no
   manual visual inspection is accepted as evidence.

## Migration Phases

### Phase 1: Extract shared logic from `agent_mux`-owned code

**Scope**: Move shared bootstrap, manifest resolution, and container contract
logic out of `src/core/orchestra_agents/agent_mux_runtime/` into
`src/core/orchestra_agents/runtime/`.

**Cutover**:

```bash
# Verify shared bootstrap is operational
PYTHONPATH=src python -c "from core.orchestra_agents.runtime.bootstrap import run_backend; print('ok')"

# Verify template mains still delegate correctly
PYTHONPATH=src python -m unittest src.core.orchestra_agents.tests.test_agent_mux_runtime_parity
```

**Rollback**:

```bash
# Restore the pre-cutover manifest snapshot for the affected agent
bash scripts/rollback_agent_manifest.sh \
  path/to/phase1/manifest.snapshot \
  path/to/agent/manifest.yaml

# Restart the affected agent container from clean state
docker compose restart <agent-container>
```

### Phase 2: Relocate backend packages

**Scope**: Move backend implementation code from `agents/<slug>/agent_runtime/`
and `agent_mux_runtime/` into `src/core/orchestra_agents/backends/{sgr,agent_mux,opencode}/`.

**Cutover**:

```bash
# Verify backend packages exist
test -d src/core/orchestra_agents/backends/sgr
test -d src/core/orchestra_agents/backends/agent_mux
test -d src/core/orchestra_agents/backends/opencode

# Run full test suite
docker compose --profile test run --rm test
```

**Rollback**:

```bash
# Restore the pre-relocation manifest snapshot for the affected agent
bash scripts/rollback_agent_manifest.sh \
  path/to/phase2/manifest.snapshot \
  path/to/agent/manifest.yaml

# Restart the affected agent container from clean state
docker compose restart <agent-container>
```

### Phase 3: Migrate `sgr_minimax` adapter

**Scope**: Ensure `sgr_minimax` backend uses the shared bootstrap path, shared
runtime contract, and lives under `src/core/orchestra_agents/backends/sgr/`.

**Cutover**:

```bash
# Verify SGR agent starts and passes health check
docker compose up -d sgr-test-agent
curl -sf http://localhost:<sgr-port>/healthz | grep ok

# Run SGR-specific regression tests
PYTHONPATH=src python -m unittest src.core.orchestra_agents.tests.test_sgr_example
```

**Rollback**:

```bash
bash scripts/rollback_agent_manifest.sh \
  path/to/sgr/manifest.snapshot \
  agents/sgr/manifest.yaml

docker compose restart sgr-test-agent
```

### Phase 4: Migrate `agent_mux` and `opencode_omo` adapters

**Scope**: Finalize `agent_mux` and `opencode_omo` as equal-status adapters
under `src/core/orchestra_agents/backends/`.

**Cutover**:

```bash
# Run cross-backend semantic parity suite
PYTHONPATH=src python -m unittest src.core.orchestra_agents.tests.test_backend_semantic_parity

# Run full integration suite
docker compose --profile test run --rm test
```

**Rollback**:

```bash
# Restore the pre-cutover manifest snapshots for the affected agents
bash scripts/rollback_agent_manifest.sh \
  path/to/agent-mux/manifest.snapshot \
  agents/orchestra/manifest.yaml
bash scripts/rollback_agent_manifest.sh \
  path/to/opencode/manifest.snapshot \
  agents/opencode-example/manifest.yaml

docker compose restart <agent-mux-container> <opencode-container>
```

### Phase 5: Final cleanup and verification

**Scope**: Remove all temporary compatibility shims, delete
`src/core/orchestra_agents/agent_mux_runtime/`, verify final repository layout.

**Cutover**:

```bash
# Verify agent_mux_runtime is fully removed
test ! -d src/core/orchestra_agents/agent_mux_runtime

# Verify no agent_runtime dirs remain under agents/
find agents/ -type d -name "agent_runtime" | grep -q . && echo "FAIL" || echo "PASS"

# Verify all backends exist under canonical location
test -d src/core/orchestra_agents/backends/sgr
test -d src/core/orchestra_agents/backends/agent_mux
test -d src/core/orchestra_agents/backends/opencode

# Full regression
docker compose --profile test run --rm test
```

**Rollback**:

```bash
# Restore the last verified manifest snapshots for affected agents
bash scripts/rollback_agent_manifest.sh \
  path/to/verified/manifest.snapshot \
  path/to/agent/manifest.yaml

# If the failure came from a controlled switch rehearsal, restore that temp manifest too
bash scripts/rollback_backend_switch.sh \
  path/to/temp/manifest.yaml.snapshot \
  path/to/temp/manifest.yaml

docker compose restart <affected-agent-container>
```

## Backward Compatibility Rules

### Manifest compatibility

- Existing manifests that use legacy `runtime.image` and `runtime.command`
  fields continue to work during migration via normalization fallback in
  manifest loading.
- Once migration completes, `runtime.image` and `runtime.command` become
  deprecated fields. The platform derives these from `backend.type`.
- Authors are not required to update manifests during migration — the
  normalization layer handles legacy format silently.

### Container contract compatibility

- All agent containers continue to expose the same HTTP endpoints:
  `/healthz`, `/event`, `/stop`, `/last_status`, `/clear_context`.
- No endpoint behavior changes occur until the corresponding migration phase
  is complete and verified.

### Backend switching contract

- Backend switching is restart-based and uses a clean-state model.
- Task 12 supports switching only for **controlled temporary manifests** created
  for verification. The supported mutation is `backend.type` only.
- The supported verification path is: snapshot manifest bytes, generate a
  controlled temporary manifest, restart from clean state, verify HTTP contract
  surface and platform-derived runtime defaults, then restore from snapshot if
  needed.
- Existing production manifests are **not** claimed to be universally
  cross-switchable across all backends.
- No backend-native state (sessions, queues, context files) survives a backend
  switch. Each restart is a fresh start.

## Task 12 Automation Commands

### Migration verification

Use the Task 12 script to validate the migration shape without editing the live
manifest:

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_agent_migration.py --agent sgr --check-only
PYTHONPATH=src .venv/bin/python scripts/verify_agent_migration.py --agent orchestra --check-only
PYTHONPATH=src .venv/bin/python scripts/verify_agent_migration.py --agent opencode-example --check-only
```

Pass criteria:

- JSON output contains `"ok": true`
- `migrated_runtime` shows the platform-derived runtime for the manifest's
  backend
- `switch_subset_supported` is treated as informational only; it does **not**
  mean arbitrary real manifests are safe to cross-switch

### Controlled backend-switch verification

Task 12 switch coverage is intentionally narrow. It creates a controlled temp
manifest, mutates `backend.type`, performs a clean restart-style verification,
probes shared contract endpoints, and records a conservative prepare-path
latency guardrail.

```bash
PYTHONPATH=src .venv/bin/python scripts/test_backend_switch.py \
  --agent sgr \
  --target-backend opencode_omo \
  --check-only
```

Pass criteria:

- JSON output contains `"ok": true`
- `mutated_fields` is exactly `["backend.type"]`
- `execution_mode` is `"restart_probe"` unless `--prepare-only` is used
- `verified` is `true`
- `threshold_ok` is `true` for the prepare path latency guardrail
- `clean_state_only` and `restart_required` are both `true`
- `contract_checks.ok` is `true`

If you need the manifest-preparation-only path for local debugging, run:

```bash
PYTHONPATH=src .venv/bin/python scripts/test_backend_switch.py \
  --agent sgr \
  --target-backend opencode_omo \
  --check-only \
  --prepare-only
```

### Snapshot-backed rollback

Rollback for Task 12 is snapshot-based. Do **not** use `git checkout`.

```bash
# Restore a manifest edited in place during migration work
bash scripts/rollback_agent_manifest.sh \
  path/to/manifest.yaml.snapshot \
  path/to/manifest.yaml

# Restore a controlled backend-switch temp manifest before the next clean restart
bash scripts/rollback_backend_switch.sh \
  path/to/temp/manifest.yaml.snapshot \
  path/to/temp/manifest.yaml
```

Pass criteria:

- JSON output contains `"ok": true`
- rollback output reports the restored manifest path and snapshot path
- backend-switch rollback output reports `restart_required: true`

## Temporary Compatibility Shim Policy

During migration, thin re-export shims may be introduced in legacy module
locations to avoid breaking downstream imports:

### Rules for temporary compatibility shims

1. **Thin forwarding only.** A shim may only re-export symbols from the new
   canonical location. It must not contain logic, validation, or state.
2. **Marked temporary.** Each shim file must contain a comment:
   `# TEMPORARY SHIM — scheduled for removal in Phase 5`
3. **Branch-local.** Shims exist only during migration branches and must not
   be merged into the final state.
4. **Deletion required.** All shims must be deleted before the final
   verification wave (F1–F4).
5. **No new dependents.** New code must import from canonical locations only.
   Shim imports are forbidden in new modules.

### Shim lifecycle

| Location | Purpose | Introduced | Removed |
|---|---|---|---|
| `agent_mux_runtime/bootstrap.py` | Re-exports `runtime.bootstrap` | Phase 1 | Phase 5 |
| `agent_mux_runtime/__init__.py` | Re-exports moved symbols | Phase 2 | Phase 5 |
| `agents/sgr/agent_runtime/main.py` | Delegates to `backends.sgr` | Phase 2 | Phase 5 |

### Final removal target

At the end of Phase 5, you must remove src/core/orchestra_agents/agent_mux_runtime
entirely. No files from this package may remain in the final repository tree.

## Verification Matrix

| Phase | Verification Command | Pass Criteria |
|---|---|---|
| Phase 1 | `PYTHONPATH=src python -m unittest src.core.orchestra_agents.tests.test_agent_mux_runtime_parity` | Exit 0 |
| Phase 2 | `docker compose --profile test run --rm test` | Exit 0 |
| Phase 3 | `PYTHONPATH=src python -m unittest src.core.orchestra_agents.tests.test_sgr_example` | Exit 0 |
| Phase 4 | `PYTHONPATH=src python -m unittest src.core.orchestra_agents.tests.test_backend_semantic_parity` | Exit 0 |
| Phase 5 | `test ! -d src/core/orchestra_agents/agent_mux_runtime && docker compose --profile test run --rm test` | Exit 0 |
| Task 12 migration | `PYTHONPATH=src .venv/bin/python scripts/verify_agent_migration.py --agent sgr --check-only` | JSON `ok=true` |
| Task 12 switch subset | `PYTHONPATH=src .venv/bin/python scripts/test_backend_switch.py --agent sgr --target-backend opencode_omo --check-only` | JSON `ok=true`, `verified=true`, `mutated_fields=["backend.type"]`, `contract_checks.ok=true` |
| Task 12 rollback | `bash scripts/rollback_backend_switch.sh <snapshot> <manifest>` | JSON `ok=true` |

## Rollback Decision Tree

```
Migration phase failed?
├── Task 12 temp manifest or migration output is wrong?
│   └── Restore exact bytes from snapshot with rollback_* script, then re-run verification
├── Backend-switch prepare path exceeds latency guardrail?
│   └── Treat as a failure. Fix the harness or shrink the work done before restart.
├── Parity test reveals semantic divergence?
│   └── Do NOT rollback. Fix the divergence in the adapter. Re-run parity suite.
└── Full regression failure after Phase 5 cleanup?
    └── Restore the appropriate manifest snapshot set with rollback_* scripts, restart from clean state, and investigate before re-attempting.
```

### Rollback scope note

The automated rollback contract in this document is **manifest/runtime rollout rollback**.
It restores exact manifest bytes from snapshots and requires a clean restart.
It is intentionally separate from source-control operations on the refactor branch.

## Scope Boundaries

- This policy covers the backend unification refactor only.
- It does not cover new backend introductions, model routing changes, or
  thread service modifications.
- Runtime hot-switching is explicitly out of scope. Only restart-based,
  clean-state backend switching is supported.
