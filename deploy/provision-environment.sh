#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/port-allocator.sh"
source "${SCRIPT_DIR}/lib/worktree-manager.sh"

usage() {
  printf 'Usage: %s <env-name> [base-env]\n' "$(basename "$0")" >&2
  exit 1
}

load_kv_env_file() {
  local env_file
  local key
  local value

  env_file="$1"
  while IFS='=' read -r key value; do
    if [[ -z "${key}" || "${key}" == \#* ]]; then
      continue
    fi
    if [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      export "${key}=${value}"
    fi
  done < "${env_file}"
}

inject_runtime_settings_into_vault() {
  local environment
  local vault_addr
  local root_token
  local ports_file

  environment="$1"
  vault_addr="$2"
  root_token="$3"
  ports_file="$4"

  python3 - "${environment}" "${vault_addr}" "${root_token}" "${ports_file}" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


def vault_request(
    url: str,
    *,
    token: str,
    method: str = 'GET',
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = None
    headers = {'X-Vault-Token': token}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode('utf-8').strip()
    return json.loads(raw) if raw else {}


environment = sys.argv[1]
vault_addr = sys.argv[2].rstrip('/')
root_token = sys.argv[3]
ports_file = Path(sys.argv[4])

ports_payload: dict[str, str] = {}
for raw_line in ports_file.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    if key.startswith('OT_PORT_') or key in (
        'OT_OMNIROUTE_DATA_DIR',
        'OT_OMNIROUTE_WET_DIR',
        'OT_SESSIONS_DIR',
    ):
        ports_payload[key] = value

base_data = vault_request(
    f'{vault_addr}/v1/kv/data/orchestrathreads/{environment}/runtime',
    token=root_token,
)['data']['data']

payload = dict(base_data)
payload.update(ports_payload)

vault_request(
    f'{vault_addr}/v1/kv/data/orchestrathreads/{environment}/runtime',
    token=root_token,
    method='POST',
    payload={'data': payload},
)
PY
}

_cleanup_on_failure() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 && -n "${_PROVISION_ENV_DIR:-}" && -d "${_PROVISION_ENV_DIR}" ]]; then
    log_error "Provisioning failed (exit ${exit_code}). Cleaning up partial state..."
    # Remove worktree if created
    remove_worktree "${_PROVISION_ENV_DIR}/workspace" 2>/dev/null || true
    # Remove Vault artifacts (best-effort)
    if [[ -n "${_PROVISION_VAULT_TOKEN:-}" ]]; then
      local va="${VAULT_ADDR:-http://127.0.0.1:8200}"
      local en="${_PROVISION_ENV_NAME:-}"
      curl -fsS -X DELETE -H "X-Vault-Token: ${_PROVISION_VAULT_TOKEN}" "${va}/v1/kv/metadata/orchestrathreads/${en}/runtime" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${_PROVISION_VAULT_TOKEN}" "${va}/v1/sys/policies/acl/orchestrathreads-${en}-runtime-read" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${_PROVISION_VAULT_TOKEN}" "${va}/v1/auth/approle/role/orchestrathreads-${en}-runtime" 2>/dev/null || true
    fi
    rm -f "${ROOT_DIR}/deploy/vault/local/${_PROVISION_ENV_NAME:-}-approle.env"
    # Remove env dir (including root-owned files)
    if [[ -d "${_PROVISION_ENV_DIR}/runtime" ]]; then
      docker run --rm -v "${_PROVISION_ENV_DIR}/runtime:/cleanup" alpine:3 rm -rf /cleanup 2>/dev/null || true
    fi
    rm -rf "${_PROVISION_ENV_DIR}"
    log_error "Cleanup complete. Re-run to try again."
  fi
}

main() {
  local env_name
  local base_env
  local envs_root
  local env_dir
  local workspace_dir
  local runtime_root
  local ports_file
  local approle_src
  local approle_dst
  local root_token_file
  local root_token
  local vault_path
  local port_key

  env_name="${1:-}"
  base_env="${2:-dev}"
  if [[ -z "${env_name}" ]]; then
    usage
  fi
  if ! validate_env_name "${env_name}"; then
    die "Invalid environment name: ${env_name}"
  fi
  if ! validate_env_name "${base_env}"; then
    die "Invalid base environment name: ${base_env}"
  fi

  require_cmd python3 >/dev/null

  export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
  require_env VAULT_ADDR >/dev/null

  envs_root="$(get_envs_root)"
  export ENVS_ROOT="${envs_root}"
  env_dir="${ENVS_ROOT}/${env_name}"
  workspace_dir="${env_dir}/workspace"
  runtime_root="${env_dir}/runtime"
  ports_file="${env_dir}/ports.env"
  approle_src="${ROOT_DIR}/deploy/vault/local/${env_name}-approle.env"
  approle_dst="${env_dir}/approle.env"
  root_token_file="${ROOT_DIR}/deploy/vault/local/root-token"
  vault_path="kv/orchestrathreads/${env_name}/runtime"

  # Env-level lock: prevent concurrent provision of the same name
  local lock_file="${envs_root}/.provision-${env_name}.lock"
  mkdir -p "${envs_root}"
  exec 201>"${lock_file}"
  flock -n 201 || die "Another provision for '${env_name}' is in progress"

  if [[ -d "${env_dir}" ]]; then
    die "Environment already exists: ${env_dir}"
  fi
  check_disk_space || die 'Insufficient disk space'

  # Set globals for cleanup trap
  _PROVISION_ENV_DIR="${env_dir}"
  _PROVISION_ENV_NAME="${env_name}"
  trap _cleanup_on_failure EXIT

  mkdir -p "${runtime_root}/omniroute-data" "${runtime_root}/omniroute-wet" "${runtime_root}/sessions"
  allocate_ports "${env_name}"
  {
    printf 'OT_OMNIROUTE_DATA_DIR=%s\n' "${runtime_root}/omniroute-data"
    printf 'OT_OMNIROUTE_WET_DIR=%s\n' "${runtime_root}/omniroute-wet"
    printf 'OT_SESSIONS_DIR=%s\n' "${runtime_root}/sessions"
  } >> "${ports_file}"

  create_worktree "${workspace_dir}"

  bash "${ROOT_DIR}/deploy/create-env.sh" "${env_name}" "${base_env}"
  if [[ ! -f "${root_token_file}" ]]; then
    die "Missing Vault root token file: ${root_token_file}"
  fi
  root_token="$(<"${root_token_file}")"
  _PROVISION_VAULT_TOKEN="${root_token}"
  inject_runtime_settings_into_vault "${env_name}" "${VAULT_ADDR}" "${root_token}" "${ports_file}"

  if [[ ! -f "${approle_src}" ]]; then
    die "Missing generated AppRole file: ${approle_src}"
  fi
  cp "${approle_src}" "${approle_dst}"

  load_kv_env_file "${ports_file}"
  load_kv_env_file "${approle_dst}"
  export COMPOSE_PROJECT_NAME="orchestrathreads-${env_name}"
  export OT_WORKSPACE_DIR="${workspace_dir}"
  export OT_WORKSPACE_MOUNT="${workspace_dir}"
  export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"

  bash "${ROOT_DIR}/deploy/deploy-env.sh" "${env_name}"

  # Success — disarm cleanup trap
  trap - EXIT
  printf 'Environment provisioned successfully\n'
  printf '  Name: %s\n' "${env_name}"
  printf '  Workspace: %s\n' "${workspace_dir}"
  printf '  Ports:\n'
  while IFS= read -r port_key; do
    printf '    %s=%s\n' "${port_key}" "${!port_key}"
  done <<'EOF'
OT_PORT_VAULT
OT_PORT_LANGFUSE
OT_PORT_THREADS
OT_PORT_EVENTS
OT_PORT_AGENTS
OT_PORT_TASK_REGISTRY
OT_PORT_SCHEDULER
OT_PORT_OMNIROUTE
OT_PORT_WET
OT_PORT_WET_ADMIN
EOF
  printf '  Vault path: %s\n' "${vault_path}"
}

main "$@"
