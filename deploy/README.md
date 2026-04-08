# Environment Provisioning System

Unified tooling for creating, deploying, and tearing down fully isolated OrchestraThreads environments on a single server.

## Quick Start

```bash
# Start or create an environment in one command
bash deploy/up-environment.sh my-feature dev

# Stop an environment in one command
bash deploy/down-environment.sh my-feature

# Ensure Vault is running and unsealed
docker compose --profile vault up -d vault
UNSEAL_KEY=$(cat deploy/vault/local/unseal-key)
docker exec -e VAULT_ADDR=http://127.0.0.1:8200 ot-dev3-vault-1 vault operator unseal "$UNSEAL_KEY"

# Provision a new environment (clones secrets from a base env)
bash deploy/provision-environment.sh my-feature prod

# List all environments
bash deploy/list-environments.sh

# Tear down an environment
bash deploy/teardown-environment.sh my-feature
```

## Command Reference

### provision-environment.sh

Creates a fully isolated environment with its own workspace, Docker containers, ports, Vault secrets, runtime state, and OmniRoute runtime API key.

```bash
bash deploy/provision-environment.sh <env-name> [base-env]
```

- `env-name` — lowercase alphanumeric + hyphens, 2-32 chars (e.g. `my-feature`, `pr-123`, `agent-qa`)
- `base-env` — environment to clone secrets from (default: `dev`)

What it does:
1. Validates environment name and checks disk space
2. Creates directory structure under `environments/<env>/`
3. Allocates 10 unique host ports (range 30000-39999)
4. Creates a git worktree (detached HEAD from current master)
5. Provisions Vault secrets (cloned from base env with isolated passwords)
6. Starts OmniRoute + WET and auto-creates the runtime API key
7. Deploys the full Docker Compose stack

### teardown-environment.sh

Stops and removes all resources for an environment.

```bash
bash deploy/teardown-environment.sh <env-name> [--force] [--keep-secrets]
```

- `--force` — required for protected environments (dev, stg, prod)
- `--keep-secrets` — preserve Vault secrets and AppRole (default: delete everything)

What it does:
1. Stops and removes Docker containers and volumes
2. Removes git worktree
3. Deletes Vault secrets, policy, and AppRole
4. Removes environment directory

### list-environments.sh

Lists all provisioned environments with status.

```bash
bash deploy/list-environments.sh [--json]
```

### deploy-env.sh

Deploys or redeploys an existing environment from Vault secrets.

```bash
bash deploy/deploy-env.sh <env-name> [--pull]
```

Supports both standard environments (dev/stg/prod) and provisioned environments. For provisioned environments, automatically detects the workspace directory and allocated ports.

`deploy-env.sh` now bootstraps OmniRoute access automatically:

1. Starts OmniRoute + WET first
2. Logs into OmniRoute with `OMNIROUTE_INITIAL_PASSWORD`
3. Creates the runtime API key `orchestrathreads-<env>-runtime`
4. Stores it back into Vault as `OMNIROUTE_API_KEY`
5. Starts the rest of the stack

The only remaining manual step is adding/logging into providers in the OmniRoute UI.

### up-environment.sh

Minimal operator entrypoint:

```bash
bash deploy/up-environment.sh <env-name> [base-env]
```

- if the environment does not exist yet, it provisions it
- if the environment already exists, it redeploys it

### down-environment.sh

Minimal operator stop command:

```bash
bash deploy/down-environment.sh <env-name>
```

This stops the compose stack and removes the env-scoped spawned agent containers.

For production-ready deploys, the OmniRoute runtime key is persisted with a constrained
writer AppRole (`orchestrathreads-<env>-runtime-writer`) instead of the Vault root token.

## Environment Structure

```
environments/
├── my-feature/
│   ├── workspace/          # git worktree (detached HEAD)
│   ├── runtime/
│   │   ├── omniroute-data/ # isolated omniroute state
│   │   ├── omniroute-wet/  # isolated wet proxy state
│   │   └── sessions/       # isolated telegram sessions
│   ├── ports.env           # allocated host ports
│   └── approle.env         # Vault AppRole credentials
├── pr-123/
│   └── ...
```

Each environment is isolated across these dimensions:
- **Docker containers** — separate `COMPOSE_PROJECT_NAME`, network, named volumes
- **Filesystem** — separate git worktree for application code, separate runtime state directories
- **Secrets** — separate Vault KV path + AppRole
- **Ports** — unique host ports, no collisions

### Known isolation boundaries

- **Docker socket**: All environments share `/var/run/docker.sock`. The `orchestra-agents` service mounts it to manage agent containers. This means an agent in one environment can technically see containers from other environments via the Docker API. This is an accepted tradeoff for the single-server architecture.
- **Git metadata**: Worktrees share the parent repository's `.git` database. This is safe for concurrent reads but means `git` operations in one worktree can affect refs visible to others.
- **Vault instance**: All environments share a single Vault server. Isolation is enforced via scoped AppRole policies (each env can only read its own `kv/orchestrathreads/<env>/runtime` path).

## Port Allocation

Each environment gets 10 sequential ports from the 30000-39999 range:

| Offset | Service | Env Variable |
|--------|---------|--------------|
| +0 | Vault | OT_PORT_VAULT |
| +1 | Langfuse | OT_PORT_LANGFUSE |
| +2 | Orchestra Threads | OT_PORT_THREADS |
| +3 | Events Engine | OT_PORT_EVENTS |
| +4 | Orchestra Agents | OT_PORT_AGENTS |
| +5 | Task Registry | OT_PORT_TASK_REGISTRY |
| +6 | Scheduler | OT_PORT_SCHEDULER |
| +7 | Omniroute | OT_PORT_OMNIROUTE |
| +8 | WET | OT_PORT_WET |
| +9 | WET Admin | OT_PORT_WET_ADMIN |

Collision detection scans existing `ports.env` files and verifies port availability with `ss`.

Standard environments (dev/stg/prod) use fixed offsets and are not managed by the port allocator.

## Vault Integration

Secrets are stored at `kv/orchestrathreads/<env>/runtime` in HashiCorp Vault.

Each environment gets:
- Scoped read-only policy: `orchestrathreads-<env>-runtime-read`
- AppRole with 1h token TTL
- Isolated passwords, secrets, and runtime paths

Provisioning clones the base environment secrets and generates:
- Unique `POSTGRES_PASSWORD`
- Unique `LANGFUSE_DB_PASSWORD`, `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`
- Unique `OMNIROUTE_INITIAL_PASSWORD`
- Environment-specific runtime paths and ports
- Cleared sensitive integrations (Telegram, Langfuse keys, Omniroute API key)

## Backward Compatibility

Standard environments (dev, stg, prod) continue to work exactly as before:
- They use the repo root as workspace (no worktree)
- They use fixed port assignments from `.env` or Vault
- `deploy-env.sh dev|stg|prod` works unchanged

The `OT_WORKSPACE_DIR` env var defaults to `.` (current directory) when unset, preserving existing behavior.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| OT_ENVS_ROOT | ./environments | Root directory for environment storage |
| OT_WORKSPACE_DIR | . | Workspace directory mounted into containers |
| VAULT_ADDR | http://127.0.0.1:8200 | Vault server address |

## Troubleshooting

### Vault is sealed after restart
```bash
UNSEAL_KEY=$(cat deploy/vault/local/unseal-key)
docker exec -e VAULT_ADDR=http://127.0.0.1:8200 ot-dev3-vault-1 vault operator unseal "$UNSEAL_KEY"
```

### Port already in use
The port allocator checks availability before assigning. If a port is blocked by an external process, try tearing down and re-provisioning:
```bash
bash deploy/teardown-environment.sh my-env
bash deploy/provision-environment.sh my-env dev
```

### Stale worktree metadata
If a worktree was removed manually:
```bash
git worktree prune
```

### Environment directory exists but stack is not running
Re-deploy without full provisioning:
```bash
bash deploy/deploy-env.sh my-env
```

### Running deploy commands from a worktree

Deploy scripts are **control-plane tools** that live in the main repository. Worktrees contain only committed application code, not uncommitted deploy scripts or local Vault artifacts.

When working inside a provisioned worktree, use **absolute paths** to the main repo's deploy scripts:

```bash
# From inside environments/my-feature/workspace/
MAIN_REPO="/path/to/OrchestraThreads"
bash "${MAIN_REPO}/deploy/deploy-env.sh" my-feature
bash "${MAIN_REPO}/deploy/list-environments.sh"
bash "${MAIN_REPO}/deploy/teardown-environment.sh" my-feature
```

All scripts use `git rev-parse --git-common-dir` to resolve the main repository root, so `ROOT_DIR`, `environments/`, and `deploy/vault/local/` always point to the correct shared control-plane location regardless of the working directory.
