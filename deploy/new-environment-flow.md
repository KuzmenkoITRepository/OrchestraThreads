# New environment flow

This is the canonical zero-to-running flow for a **new** OrchestraThreads environment.

## What is automatic

- Vault unseal + AppRole-based secret rendering
- Environment workspace creation (`environments/<env>/workspace`)
- Runtime directories and port allocation
- Docker stack startup
- OmniRoute instance password provisioning via `OMNIROUTE_INITIAL_PASSWORD`
- OmniRoute runtime API key creation and storage in Vault as `OMNIROUTE_API_KEY`
- Vault persistence via a constrained writer AppRole, not the Vault root token

## What remains manual

Exactly one OmniRoute step remains manual:

1. Open the OmniRoute UI for the new environment.
2. Log in with the generated instance password.
3. Connect or log into the required LLM providers.

After providers are connected, agents can route requests immediately using the already-generated runtime API key.

## Provisioning a new isolated environment

```bash
bash deploy/provision-environment.sh <env-name> <base-env>
```

Example:

```bash
bash deploy/provision-environment.sh prod-v2 prod
```

The script now does this in order:

1. Creates the workspace and runtime directories.
2. Clones the base Vault runtime secret and regenerates environment-specific passwords.
3. Starts OmniRoute + WET first.
4. Logs into OmniRoute with `OMNIROUTE_INITIAL_PASSWORD`.
5. Creates a runtime API key named `orchestrathreads-<env>-runtime`.
6. Stores that key back into Vault as `OMNIROUTE_API_KEY`.
7. Starts the full stack.
8. Prints the operator handoff block with:
   - OmniRoute UI URL
   - OmniRoute password
   - runtime API key name
   - the remaining manual provider-login step

## Deploying prod from zero

1. Bootstrap Vault once.
2. Populate `kv/orchestrathreads/prod/runtime` with production secrets.
3. Add approval files:
   - `deploy/approvals/<ref>.approved-by-orchestra`
   - `deploy/approvals/<ref>.approved-by-qa`
4. Deploy:

```bash
OT_DEPLOY_REF=<ref> bash deploy/deploy-env.sh prod
```

During deploy, `deploy-env.sh` now performs the OmniRoute runtime-key bootstrap automatically before starting agent services.

## Operator handoff checklist

After deploy/provision finishes, do this:

1. Open the printed OmniRoute URL.
2. Log in with the printed OmniRoute password.
3. Add providers or complete OAuth login for the providers you want.
4. Verify available models in the UI.
5. Send a real event/message into the environment.

No manual Vault patching for `OMNIROUTE_API_KEY` is required anymore.

The production-ready path uses a dedicated `orchestrathreads-<env>-runtime-writer` AppRole
with access only to `kv/orchestrathreads/<env>/runtime`.
