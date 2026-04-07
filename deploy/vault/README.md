## Vault deployment scaffolding (dev/stg/prod)

This folder provides practical HashiCorp Vault scaffolding for one-server, multi-environment (`dev`, `stg`, `prod`) deployment with AppRole.

`vault-config.hcl` is optional local-only scaffolding. Docker Compose publishes Vault only on `127.0.0.1:8200` at the host boundary, while the container listener stays on `0.0.0.0:8200`. It still keeps `tls_disable=1`, so do not reuse it as a staging/production baseline.

### Goals

- Keep existing `.env` support intact.
- Render environment-specific runtime env files at deploy layer.
- Isolate secrets by environment path in Vault KV v2:
  - `kv/data/orchestrathreads/dev/runtime`
  - `kv/data/orchestrathreads/stg/runtime`
  - `kv/data/orchestrathreads/prod/runtime`
- Use separate AppRole per environment.

### Layout

- `vault-config.hcl` — optional local Vault server config.
- `bootstrap/bootstrap-vault.sh` — idempotent bootstrap for KV, policies, AppRoles.
- `bootstrap/policies/*.hcl` — environment-scoped AppRole policies.
- `bootstrap/templates/runtime.env.tpl` — runtime env template for rendered files.

### Bootstrap Vault

Assumes Vault is already initialized and unsealed.

```bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="<root-or-admin-token>"
bash deploy/vault/bootstrap/bootstrap-vault.sh
```

Bootstrap prints generated role IDs and initial secret IDs to:

- `deploy/vault/bootstrap/.out/dev.env`
- `deploy/vault/bootstrap/.out/stg.env`
- `deploy/vault/bootstrap/.out/prod.env`

Treat these files as sensitive bootstrap artifacts.

Bootstrap does **not** seed placeholder runtime secrets. It only ensures KV/AppRole/policies and prints the runtime paths you must populate explicitly.

### Write environment secrets

Example for `dev`:

```bash
vault kv put kv/orchestrathreads/dev/runtime \
  OT_PORT_THREADS="8788" \
  OT_PORT_EVENTS="8789" \
  OT_PORT_AGENTS="8790" \
  OT_PORT_TASK_REGISTRY="8791" \
  OT_PORT_SCHEDULER="8792" \
  OT_PORT_LANGFUSE="3000" \
  OT_PORT_OMNIROUTE="20229" \
  OT_PORT_WET="8100" \
  OT_PORT_WET_ADMIN="8101" \
  OT_PORT_VAULT="8200" \
  OT_OMNIROUTE_DATA_DIR="./runtime_state/orchestrathreads-dev/omniroute-data" \
  OT_OMNIROUTE_WET_DIR="./runtime_state/orchestrathreads-dev/omniroute-wet" \
  OT_SESSIONS_DIR="./runtime_state/orchestrathreads-dev/sessions" \
  POSTGRES_PASSWORD="..." \
  ORCHESTRA_THREADS_DATABASE_URL="..." \
  OMNIROUTE_API_KEY="..." \
  TELEGRAM_API_ID="..." \
  TELEGRAM_API_HASH="..." \
  TELEGRAM_SESSION_STRING="..."
```

### Render deploy env and run stack

```bash
bash deploy/deploy-env.sh dev
```

This script:

1. Logs into Vault with env-specific AppRole.
2. Reads `kv/orchestrathreads/<env>/runtime`.
3. Renders `deploy/runtime_env/<env>.env`.
4. Runs `docker compose --env-file <rendered-file> up -d`.
5. Removes the rendered env file by default after deploy.

Any environment name is supported as long as a matching AppRole file exists in `deploy/vault/local/<environment>-approle.env`.

### Create additional environments

You can provision a new isolated environment from an existing base (default: `dev`):

```bash
export VAULT_ADDR="http://127.0.0.1:8200"
bash deploy/create-env.sh qa dev
```

This will:

1. Copy the base environment secret payload from Vault.
2. Generate isolated passwords/secrets and runtime paths.
3. Create a Vault policy and AppRole for the new environment.
4. Write `deploy/vault/local/qa-approle.env`.

Then deploy it with:

```bash
bash deploy/deploy-env.sh qa
```

### Required deploy-time variables

Set these in shell or in your host-level deploy configuration:

- `VAULT_ADDR`
- `VAULT_ROLE_ID_DEV` / `VAULT_SECRET_ID_DEV`
- `VAULT_ROLE_ID_STG` / `VAULT_SECRET_ID_STG`
- `VAULT_ROLE_ID_PROD` / `VAULT_SECRET_ID_PROD`
- `OT_DEPLOY_REF` for prod deployments

Optional:

- `COMPOSE_PROJECT_PREFIX` (default: `orchestrathreads`)
- `OT_RUNTIME_ENV_TEMPLATE` (template path override)
- `OT_KEEP_RUNTIME_ENV_FILE=1` to keep the rendered env file for debugging

### Production approval gate

Prod deploys require approval artifacts under `deploy/approvals/`:

- `deploy/approvals/<OT_DEPLOY_REF>.approved-by-orchestra`
- `deploy/approvals/<OT_DEPLOY_REF>.approved-by-qa`

Without both files, `deploy/deploy-env.sh prod` refuses to deploy.
