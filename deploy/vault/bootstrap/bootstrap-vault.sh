#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_DIR="${SCRIPT_DIR}/policies"
OUTPUT_DIR="${SCRIPT_DIR}/.out"
APP_PREFIX="orchestrathreads"
ENVIRONMENTS=(dev stg prod)
README_PREFIX='Populate runtime secrets explicitly with `vault kv put kv/orchestrathreads/<env>/runtime ...` before deploy.'

_require_cmd() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required command missing: %s\n' "${command_name}" >&2
    exit 1
  fi
}

_require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf 'Required environment variable missing: %s\n' "${name}" >&2
    exit 1
  fi
}

_write_policy() {
  local environment="$1"
  local policy_name="${APP_PREFIX}-${environment}-runtime-read"
  vault policy write "${policy_name}" "${POLICY_DIR}/${environment}.hcl" >/dev/null
  printf 'Policy ensured: %s\n' "${policy_name}"
}

_write_writer_policy() {
  local environment="$1"
  local policy_name="${APP_PREFIX}-${environment}-runtime-write"
  vault policy write "${policy_name}" "${POLICY_DIR}/${environment}-writer.hcl" >/dev/null
  printf 'Policy ensured: %s\n' "${policy_name}"
}

_enable_approle() {
  if vault auth list -format=json | jq -e 'has("approle/")' >/dev/null; then
    return
  fi
  vault auth enable approle >/dev/null
  printf 'Enabled AppRole auth method\n'
}

_ensure_kv_v2() {
  if vault secrets list -format=json | jq -e 'has("kv/")' >/dev/null; then
    return
  fi
  vault secrets enable -path=kv kv-v2 >/dev/null
  printf 'Enabled KV v2 at kv/\n'
}

_write_role_credentials() {
  local environment="$1"
  local role_name="${APP_PREFIX}-${environment}-runtime"
  local policy_name="${APP_PREFIX}-${environment}-runtime-read"
  local output_file="${OUTPUT_DIR}/${environment}.env"

  vault write "auth/approle/role/${role_name}" \
    token_policies="${policy_name}" \
    token_ttl="1h" \
    token_max_ttl="4h" \
    secret_id_ttl="720h" \
    secret_id_num_uses=0 >/dev/null

  local role_id
  role_id="$(vault read -field=role_id "auth/approle/role/${role_name}/role-id")"
  local secret_id
  secret_id="$(vault write -f -field=secret_id "auth/approle/role/${role_name}/secret-id")"

  cat >"${output_file}" <<EOF
VAULT_ROLE_NAME_${environment^^}=${role_name}
VAULT_ROLE_ID_${environment^^}=${role_id}
VAULT_SECRET_ID_${environment^^}=${secret_id}
EOF

  chmod 600 "${output_file}"
  printf 'AppRole ensured: %s (credentials in %s)\n' "${role_name}" "${output_file}"
}

_write_writer_role_credentials() {
  local environment="$1"
  local role_name="${APP_PREFIX}-${environment}-runtime-writer"
  local policy_name="${APP_PREFIX}-${environment}-runtime-write"
  local output_file="${OUTPUT_DIR}/${environment}.env"

  vault write "auth/approle/role/${role_name}" \
    token_policies="${policy_name}" \
    token_ttl="15m" \
    token_max_ttl="1h" \
    secret_id_ttl="720h" \
    secret_id_num_uses=0 >/dev/null

  local role_id
  role_id="$(vault read -field=role_id "auth/approle/role/${role_name}/role-id")"
  local secret_id
  secret_id="$(vault write -f -field=secret_id "auth/approle/role/${role_name}/secret-id")"

  cat >>"${output_file}" <<EOF
VAULT_WRITER_ROLE_NAME_${environment^^}=${role_name}
VAULT_WRITER_ROLE_ID_${environment^^}=${role_id}
VAULT_WRITER_SECRET_ID_${environment^^}=${secret_id}
EOF

  chmod 600 "${output_file}"
  printf 'AppRole ensured: %s (credentials in %s)\n' "${role_name}" "${output_file}"
}

_secret_exists() {
  local environment="$1"
  vault kv get -format=json "kv/orchestrathreads/${environment}/runtime" >/dev/null 2>&1
}

_print_secret_setup_instructions() {
  local environment="$1"
  cat <<EOF
Runtime secret path ready for ${environment}: kv/orchestrathreads/${environment}/runtime
Populate it before deploy. Required keys are defined in deploy/vault/bootstrap/templates/runtime.env.tpl.
${README_PREFIX}
EOF
}

main() {
  _require_cmd vault
  _require_cmd jq
  _require_env VAULT_ADDR
  _require_env VAULT_TOKEN

  mkdir -p "${OUTPUT_DIR}"

  _ensure_kv_v2
  _enable_approle

  local environment
  for environment in "${ENVIRONMENTS[@]}"; do
    _write_policy "${environment}"
    _write_writer_policy "${environment}"
    _write_role_credentials "${environment}"
    _write_writer_role_credentials "${environment}"
    if _secret_exists "${environment}"; then
      printf 'Secret path already exists: kv/orchestrathreads/%s/runtime\n' "${environment}"
    else
      _print_secret_setup_instructions "${environment}"
    fi
  done

  printf 'Vault bootstrap complete. Secure files under %s\n' "${OUTPUT_DIR}"
}

main "$@"
