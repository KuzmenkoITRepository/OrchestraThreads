#!/usr/bin/env bash

set -euo pipefail

# Source common.sh for git-aware ROOT_DIR resolution (works from worktrees too)
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
RUNTIME_ENV_DIR="${ROOT_DIR}/deploy/runtime_env"
APPROVAL_DIR="${ROOT_DIR}/deploy/approvals"
DEFAULT_TEMPLATE="${ROOT_DIR}/deploy/vault/bootstrap/templates/runtime.env.tpl"
VAULT_SECRET_PREFIX="kv/data/orchestrathreads"

_usage() {
  printf 'Usage: %s <environment> [--pull]\n' "$(basename "$0")" >&2
  exit 1
}

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

_secret_ref_for_env() {
  local environment="$1"
  local approle_file="${ROOT_DIR}/deploy/vault/local/${environment}-approle.env"

  case "${environment}" in
    dev)
      printf '%s' 'VAULT_ROLE_ID_DEV VAULT_SECRET_ID_DEV'
      ;;
    stg)
      printf '%s' 'VAULT_ROLE_ID_STG VAULT_SECRET_ID_STG'
      ;;
    prod)
      printf '%s' 'VAULT_ROLE_ID_PROD VAULT_SECRET_ID_PROD'
      ;;
    *)
      if [[ -f "${approle_file}" ]]; then
        printf '%s' "${approle_file}"
        return
      fi
      _usage
      ;;
  esac
}

_load_env_from_file() {
  local env_file="$1"
  python3 - "$env_file" <<'PY'
from __future__ import annotations

import shlex
import sys
from pathlib import Path

for raw_line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    print(f'{key}={shlex.quote(value)}')
PY
}

_require_prod_approvals() {
  local deploy_ref="${OT_DEPLOY_REF:-}"
  local orchestra_file
  local qa_file

  if [[ -z "${deploy_ref}" ]]; then
    printf 'Missing production deploy reference: OT_DEPLOY_REF\n' >&2
    exit 1
  fi
  orchestra_file="${APPROVAL_DIR}/${deploy_ref}.approved-by-orchestra"
  qa_file="${APPROVAL_DIR}/${deploy_ref}.approved-by-qa"
  if [[ ! -f "${orchestra_file}" ]]; then
    printf 'Missing production approval file: %s\n' "${orchestra_file}" >&2
    exit 1
  fi
  if [[ ! -f "${qa_file}" ]]; then
    printf 'Missing production approval file: %s\n' "${qa_file}" >&2
    exit 1
  fi
}

_vault_login_approle() {
  local role_id_var="$1"
  local secret_id_var="$2"
  local role_id="${!role_id_var}"
  local secret_id="${!secret_id_var}"

  curl -fsS \
    -H 'Content-Type: application/json' \
    -X POST \
    -d "$(jq -cn --arg role_id "${role_id}" --arg secret_id "${secret_id}" '{role_id: $role_id, secret_id: $secret_id}')" \
    "${VAULT_ADDR}/v1/auth/approle/login" | jq -r '.auth.client_token'
}

_read_runtime_json() {
  local environment="$1"
  local vault_token="$2"
  local secret_path="${VAULT_SECRET_PREFIX}/${environment}/runtime"
  curl -fsS \
    -H "X-Vault-Token: ${vault_token}" \
    "${VAULT_ADDR}/v1/${secret_path}" | jq -c '.data.data'
}

_validate_prod_runtime_json() {
  local runtime_json="$1"
  python3 - "$runtime_json" <<'PY'
from __future__ import annotations

import json
import sys

runtime_data = json.loads(sys.argv[1])
required_keys = (
    "POSTGRES_PASSWORD",
    "ORCHESTRA_THREADS_DATABASE_URL",
    "LANGFUSE_NEXTAUTH_SECRET",
    "LANGFUSE_SALT",
    "OMNIROUTE_INITIAL_PASSWORD",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
)
placeholder_markers = ("change-me", "changeme", "placeholder", "replace-me", "orchestra")

missing = []
weak = []
for key in required_keys:
    raw_value = str(runtime_data.get(key, "")).strip()
    if not raw_value:
        missing.append(key)
        continue
    normalized = raw_value.lower()
    if any(marker in normalized for marker in placeholder_markers):
        weak.append(key)

if missing or weak:
    problems: list[str] = []
    if missing:
        problems.append(f"missing required prod keys: {', '.join(missing)}")
    if weak:
        problems.append(f"placeholder-like prod keys: {', '.join(weak)}")
    raise SystemExit("; ".join(problems))
PY
}

_render_runtime_env_file() {
  local template_path="$1"
  local runtime_json="$2"
  local output_path="$3"

  python3 - "$template_path" "$runtime_json" "$output_path" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

template_path = Path(sys.argv[1])
runtime_data = json.loads(sys.argv[2])
output_path = Path(sys.argv[3])

pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
template_text = template_path.read_text(encoding="utf-8")
keys = sorted(set(pattern.findall(template_text)))

missing = [key for key in keys if key not in runtime_data]
if missing:
    raise SystemExit(f"Missing keys in Vault secret payload: {', '.join(missing)}")

rendered = template_text
for key in keys:
    value = str(runtime_data[key])
    if "\n" in value or "\r" in value:
        raise SystemExit(f"Multiline value is not supported for env key: {key}")
    rendered = rendered.replace(f"${{{key}}}", value)

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(rendered, encoding="utf-8")
PY
}

main() {
  local environment="${1:-}"
  local pull_flag="${2:-}"
  local role_pair
  local approle_file
  local role_id_var
  local secret_id_var
  local template_path
  local vault_token
  local runtime_json
  local output_env_file
  local project_prefix
  local project_name
  local env_dir
  local env_ports_file

  if [[ -z "${environment}" ]]; then
    _usage
  fi
  if [[ "${pull_flag}" != "" && "${pull_flag}" != "--pull" ]]; then
    _usage
  fi

  _require_cmd jq
  _require_cmd curl
  _require_cmd docker
  : "${VAULT_ADDR:=http://127.0.0.1:8200}"
  _require_env VAULT_ADDR

  # Auto-detect provisioned environment workspace and ports
  env_dir="$(get_envs_root)/${environment}"
  if [[ -n "${env_dir}" && -d "${env_dir}" ]]; then
    if [[ -d "${env_dir}/workspace" && -z "${OT_WORKSPACE_DIR:-}" ]]; then
      export OT_WORKSPACE_DIR="${env_dir}/workspace"
      export OT_WORKSPACE_MOUNT="${env_dir}/workspace"
    fi
    env_ports_file="${env_dir}/ports.env"
    if [[ -f "${env_ports_file}" ]]; then
      set -a
      source "${env_ports_file}"
      set +a
    fi
    # Prefer per-env approle over deploy/vault/local copy
    if [[ -f "${env_dir}/approle.env" ]]; then
      eval "$(_load_env_from_file "${env_dir}/approle.env")"
      local env_var_suffix_auto="${environment^^}"
      env_var_suffix_auto="${env_var_suffix_auto//-/_}"
      role_id_var="VAULT_ROLE_ID_${env_var_suffix_auto}"
      secret_id_var="VAULT_SECRET_ID_${env_var_suffix_auto}"
    fi
  fi

  if [[ "${environment}" == "prod" ]]; then
    _require_prod_approvals
  fi

  # Resolve AppRole credentials (skip if already loaded from per-env approle)
  if [[ -z "${role_id_var:-}" || -z "${secret_id_var:-}" ]]; then
    role_pair="$(_secret_ref_for_env "${environment}")"
    if [[ "${role_pair}" == *.env ]]; then
      approle_file="${role_pair}"
      eval "$(_load_env_from_file "${approle_file}")"
      local env_var_suffix="${environment^^}"
      env_var_suffix="${env_var_suffix//-/_}"
      role_id_var="VAULT_ROLE_ID_${env_var_suffix}"
      secret_id_var="VAULT_SECRET_ID_${env_var_suffix}"
    else
      role_id_var="${role_pair%% *}"
      secret_id_var="${role_pair##* }"
    fi
  fi

  _require_env "${role_id_var}"
  _require_env "${secret_id_var}"

  vault_token="$(_vault_login_approle "${role_id_var}" "${secret_id_var}")"

  runtime_json="$(_read_runtime_json "${environment}" "${vault_token}")"
  if [[ "${environment}" == "prod" ]]; then
    _validate_prod_runtime_json "${runtime_json}"
  fi
  template_path="${OT_RUNTIME_ENV_TEMPLATE:-${DEFAULT_TEMPLATE}}"
  output_env_file="${RUNTIME_ENV_DIR}/${environment}.env"
  _render_runtime_env_file "${template_path}" "${runtime_json}" "${output_env_file}"
  chmod 600 "${output_env_file}"

  project_prefix="${COMPOSE_PROJECT_PREFIX:-orchestrathreads}"
  project_name="${project_prefix}-${environment}"
  export COMPOSE_PROJECT_NAME="${project_name}"
  export OT_RUNTIME_ENV_FILE="${output_env_file}"

  if [[ "${pull_flag}" == "--pull" ]]; then
    docker compose --env-file "${output_env_file}" pull
  fi
  docker compose --env-file "${output_env_file}" up -d

  if [[ "${OT_KEEP_RUNTIME_ENV_FILE:-0}" != "1" ]]; then
    rm -f "${output_env_file}"
  fi

  printf 'Deployed environment %s with project name %s\n' "${environment}" "${project_name}"
  if [[ "${OT_KEEP_RUNTIME_ENV_FILE:-0}" == "1" ]]; then
    printf 'Rendered env file kept at: %s\n' "${output_env_file}"
  else
    printf 'Rendered env file removed after deploy\n'
  fi
}

main "$@"
