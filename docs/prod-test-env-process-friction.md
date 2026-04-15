# Prod test environment bring-up friction log

This file captures every blocker, workaround, and extra manual step encountered while bringing up the `prod` environment for testing.

## 2026-04-11

- `deploy/deploy-env.sh prod` requires `OT_DEPLOY_REF` plus two approval artifacts under `deploy/approvals/` for that exact ref.
- Current checkout at the time of startup attempt was `95ea925` on `master`, but approval files existed only for `0df818b` and `b7ed871`.
- Operational impact: a straightforward “start prod now” request cannot target the current code without a separate approval-preparation step.
- Temporary handling: select an already-approved ref for the bring-up attempt instead of the current `HEAD`.

- Vault bootstrap/AppRole material exists in two places with divergent `VAULT_SECRET_ID_PROD` / writer secret values:
  - `deploy/vault/local/prod-approle.env`
  - `deploy/vault/bootstrap/.out/prod.env`
- Operational impact: ambiguous source of truth for production AppRole credentials increases the chance of using stale secrets during urgent bring-up.

- Starting the Vault profile and querying seal status immediately caused a transient `curl: (56) Recv failure: Connection reset by peer`.
- Operational impact: even the first health probe may fail unless operators manually retry after container startup.

- Canonical prod deploy on approved ref `0df818b` progressed through workspace preparation and startup of `orchestra-omniroute`, then failed inside `deploy/bootstrap-omniroute.sh` with HTTP `401`.
- Operational impact: `deploy/deploy-env.sh prod` can leave the environment partially started and require manual diagnosis across OmniRoute credentials, readiness, and Vault-stored runtime values.

- The prod OmniRoute instance reports `setupComplete=true` while using a persistent host bind mount at `runtime_state/orchestrathreads-prod/omniroute-data`.
- Operational impact: bootstrap behavior depends on prior local state, but the deploy flow does not explain or guard against drift between persisted OmniRoute state and Vault-held `OMNIROUTE_INITIAL_PASSWORD` / `OMNIROUTE_API_KEY` values.

- Root cause of the observed deploy failure: `deploy/bootstrap-omniroute.sh` validated an existing OmniRoute runtime API key against `GET /api/keys`, but the live OmniRoute instance accepted the same key on runtime endpoint `GET /v1/models` and rejected it on management/auth endpoints.
- Operational impact: deploy-time validation was coupled to a management route with different auth semantics than the runtime API key flow, causing false-negative bootstrap failures.

- After the bootstrap fix, canonical `prod` deploy progressed further but failed when `agent-log-analysis` tried to bind `127.0.0.1:8794`; the port was already allocated by another running container.
- Operational impact: prod startup still depends on host-global port availability, so parallel local environments can block a supposedly isolated bring-up.

- Temporary handling used for this bring-up: set `OT_PORT_AGENT_LOG_ANALYSIS=8795` in the prod Vault runtime payload so the external host bind no longer collides with the already-running `mempalace` container on `127.0.0.1:8794`.
- Follow-up issue: despite updating the Vault runtime payload, the subsequent deploy still attempted to bind `127.0.0.1:8794`, indicating that either the runtime env template or rendered env path does not propagate `OT_PORT_AGENT_LOG_ANALYSIS` as expected.
- Root cause of that follow-up issue: `deploy/vault/bootstrap/templates/runtime.env.tpl` did not include `OT_PORT_AGENT_LOG_ANALYSIS`, so the rendered `deploy/runtime_env/prod.env` silently dropped the override and Compose fell back to default port `8794`.
- Further collision discovered after fixing template propagation: chosen fallback port `8795` was already in use by `telegram-events`, so the environment still requires a port-selection step that is aware of all published host ports, not just one conflicting container.
- Service-specific follow-up issue: `agent-log-analysis` also relied on runtime env keys that were not rendered into `deploy/runtime_env/prod.env`, causing fallback to default values and an attempted Postgres login with `orchestra:orchestra` instead of the Vault-managed production credentials.
- Root cause: the runtime env template omitted `AGENT_LOG_ANALYSIS_HOST`, `AGENT_LOG_ANALYSIS_PORT`, `AGENT_LOG_ANALYSIS_DATABASE_URL`, `AGENT_LOG_ANALYSIS_DB_SCHEMA`, and `AGENT_LOG_ANALYSIS_INGEST_TOKEN`, so the service silently booted with Docker Compose defaults whenever those values were not injected another way.
- After restoring those template variables and writing explicit prod runtime values, `agent-log-analysis` still exited after startup, so a fresh service-level diagnosis was required instead of assuming the earlier password error was fully resolved.
