#!/usr/bin/env bash

set -euo pipefail

# Source common.sh for git-aware ROOT_DIR resolution (works from worktrees too)
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/worktree-manager.sh"
RUNTIME_ENV_DIR="${ROOT_DIR}/deploy/runtime_env"
APPROVAL_DIR="${ROOT_DIR}/deploy/approvals"
DEFAULT_TEMPLATE="${ROOT_DIR}/deploy/vault/bootstrap/templates/runtime.env.tpl"
DEFAULT_BETTER_TELEGRAM_MCP_URL="http://better-telegram-mcp:3000/mcp"
DEFAULT_BETTER_TELEGRAM_MCP_EVENTS_URL="http://better-telegram-mcp:3000/events/telegram"
VAULT_SECRET_PREFIX="kv/data/orchestrathreads"
VAULT_LOCAL_DIR="${ROOT_DIR}/deploy/vault/local"
BOOTSTRAP_OUT_DIR="${ROOT_DIR}/deploy/vault/bootstrap/.out"
OMNIROUTE_BOOTSTRAP_SCRIPT="${ROOT_DIR}/deploy/bootstrap-omniroute.sh"

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

_vault_container_name() {
  env -u COMPOSE_PROJECT_NAME docker compose --profile vault ps -q vault 2>/dev/null | head -1
}

_ensure_vault() {
  local unseal_key_file="${VAULT_LOCAL_DIR}/unseal-key"
  local container_id

  # Start vault container if not running
  container_id="$(_vault_container_name)"
  if [[ -z "${container_id}" ]]; then
    printf 'Starting Vault container...\n' >&2
    env -u COMPOSE_PROJECT_NAME docker compose --profile vault up -d vault >&2
    sleep 2
    container_id="$(_vault_container_name)"
  fi

  if [[ -z "${container_id}" ]]; then
    printf 'Failed to start Vault container\n' >&2
    exit 1
  fi

  # Check seal status and unseal if needed
  local sealed
  sealed="$(curl -fsS "${VAULT_ADDR}/v1/sys/seal-status" 2>/dev/null | jq -r '.sealed' 2>/dev/null || echo 'unknown')"

  if [[ "${sealed}" == "true" ]]; then
    if [[ ! -f "${unseal_key_file}" ]]; then
      printf 'Vault is sealed and no unseal key found at %s\n' "${unseal_key_file}" >&2
      exit 1
    fi
    printf 'Unsealing Vault...\n' >&2
    curl -fsS \
      -H 'Content-Type: application/json' \
      -X POST \
      -d "$(jq -cn --arg key "$(cat "${unseal_key_file}")" '{key: $key}')" \
      "${VAULT_ADDR}/v1/sys/unseal" >/dev/null
  fi
}

_read_local_root_token() {
  local root_token_file="${VAULT_LOCAL_DIR}/root-token"
  if [[ ! -f "${root_token_file}" ]]; then
    return 0
  fi
  cat "${root_token_file}"
}

_ensure_env_workspace() {
  local environment="$1"
  local envs_root
  local env_dir
  local workspace_dir

  envs_root="$(get_envs_root)"
  env_dir="${envs_root}/${environment}"
  workspace_dir="${env_dir}/workspace"

  # Update existing workspace to deploy ref if specified
  if [[ -d "${workspace_dir}" ]]; then
    if [[ -n "${OT_DEPLOY_REF:-}" ]]; then
      printf 'Updating workspace to %s...\n' "${OT_DEPLOY_REF}" >&2
      update_worktree "${workspace_dir}" "${OT_DEPLOY_REF}"
    fi
    return 0
  fi

  # Skip if OT_WORKSPACE_DIR is already set externally
  if [[ -n "${OT_WORKSPACE_DIR:-}" ]]; then
    return 0
  fi

  printf 'Bootstrapping workspace for %s...\n' "${environment}" >&2
  mkdir -p "${env_dir}"
  create_worktree "${workspace_dir}"

  # Create writable runtime_state dirs for agents that need persistent state.
  # These directories are written by agent containers running as non-root
  # (appuser uid 10001), so they require world-writable permissions.
  local agent_dir
  for agent_dir in "${workspace_dir}"/agents/*/; do
    if [[ -d "${agent_dir}" ]]; then
      mkdir -p "${agent_dir}/runtime_state"
      chmod 777 "${agent_dir}/runtime_state"
    fi
  done

  printf 'Workspace created at %s\n' "${workspace_dir}" >&2
}

_load_bootstrap_approle() {
  local environment="$1"
  local bootstrap_file="${BOOTSTRAP_OUT_DIR}/${environment}.env"

  if [[ ! -f "${bootstrap_file}" ]]; then
    return 1
  fi
  eval "$(_load_env_from_file "${bootstrap_file}")"
}

_json_get_value() {
  local runtime_json="$1"
  local key_name="$2"
  python3 - "$runtime_json" "$key_name" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
value = payload.get(sys.argv[2], "")
print(value if isinstance(value, str) else str(value))
PY
}

_json_set_value() {
  local runtime_json="$1"
  local key_name="$2"
  local key_value="$3"
  python3 - "$runtime_json" "$key_name" "$key_value" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
payload[sys.argv[2]] = sys.argv[3]
print(json.dumps(payload))
PY
}

_secret_ref_for_env() {
  local environment="$1"
  local approle_file="${ROOT_DIR}/deploy/vault/local/${environment}-approle.env"
  local env_var_suffix="${environment^^}"
  env_var_suffix="${env_var_suffix//-/_}"
  local role_var="VAULT_ROLE_ID_${env_var_suffix}"
  local secret_var="VAULT_SECRET_ID_${env_var_suffix}"

  # If env vars already set (from bootstrap auto-load or manual export)
  if [[ -n "${!role_var:-}" && -n "${!secret_var:-}" ]]; then
    printf '%s' "${role_var} ${secret_var}"
    return
  fi

  # Try per-env approle file
  if [[ -f "${approle_file}" ]]; then
    printf '%s' "${approle_file}"
    return
  fi

  # Fallback: return var names (will fail at _require_env if not set)
  printf '%s' "${role_var} ${secret_var}"
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
    "BETTER_TELEGRAM_MCP_TOKEN",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
)
placeholder_markers = ("change-me", "changeme", "placeholder", "replace-me")

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
  local writer_role_id_var
  local writer_secret_id_var
  local template_path
  local vault_token
  local runtime_json
  local output_env_file
  local project_prefix
  local project_name
  local env_dir
  local env_ports_file
  local omniroute_password
  local omniroute_api_key
  local omniroute_bootstrap_json
  local omniroute_bootstrap_status
  local omniroute_api_key_name
  local omniroute_write_token
  local omniroute_base_url

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
  export VAULT_ADDR

  _ensure_vault

  # Bootstrap workspace for base environments that lack a provisioned worktree
  _ensure_env_workspace "${environment}"

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
      writer_role_id_var="VAULT_WRITER_ROLE_ID_${env_var_suffix_auto}"
      writer_secret_id_var="VAULT_WRITER_SECRET_ID_${env_var_suffix_auto}"
    fi
  fi

  if [[ "${environment}" == "prod" ]]; then
    _require_prod_approvals
  fi

  # Resolve AppRole credentials (skip if already loaded from per-env approle)
  if [[ -z "${role_id_var:-}" || -z "${secret_id_var:-}" ]]; then
    # Try bootstrap output file first (auto-load without manual export)
    local bootstrap_file="${BOOTSTRAP_OUT_DIR}/${environment}.env"
    if [[ -f "${bootstrap_file}" ]]; then
      eval "$(_load_env_from_file "${bootstrap_file}")"
    fi

    role_pair="$(_secret_ref_for_env "${environment}")"
    if [[ "${role_pair}" == *.env ]]; then
      approle_file="${role_pair}"
      eval "$(_load_env_from_file "${approle_file}")"
      local env_var_suffix="${environment^^}"
      env_var_suffix="${env_var_suffix//-/_}"
      role_id_var="VAULT_ROLE_ID_${env_var_suffix}"
      secret_id_var="VAULT_SECRET_ID_${env_var_suffix}"
      writer_role_id_var="VAULT_WRITER_ROLE_ID_${env_var_suffix}"
      writer_secret_id_var="VAULT_WRITER_SECRET_ID_${env_var_suffix}"
    else
      role_id_var="${role_pair%% *}"
      secret_id_var="${role_pair##* }"
    fi
  fi

  _require_env "${role_id_var}"
  _require_env "${secret_id_var}"

  vault_token="$(_vault_login_approle "${role_id_var}" "${secret_id_var}")"

  runtime_json="$(_read_runtime_json "${environment}" "${vault_token}")"
  if [[ -z "$(_json_get_value "${runtime_json}" "BETTER_TELEGRAM_MCP_URL")" ]]; then
    runtime_json="$(_json_set_value "${runtime_json}" "BETTER_TELEGRAM_MCP_URL" "${DEFAULT_BETTER_TELEGRAM_MCP_URL}")"
  fi
  if [[ -z "$(_json_get_value "${runtime_json}" "BETTER_TELEGRAM_MCP_EVENTS_URL")" ]]; then
    runtime_json="$(_json_set_value "${runtime_json}" "BETTER_TELEGRAM_MCP_EVENTS_URL" "${DEFAULT_BETTER_TELEGRAM_MCP_EVENTS_URL}")"
  fi
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
  export COMPOSE_IGNORE_ORPHANS=true
  export OT_AGENT_CONTAINER_PREFIX="${project_name}-agent-"
  export OT_RUNTIME_ENV_FILE="${output_env_file}"
  omniroute_password="$(_json_get_value "${runtime_json}" "OMNIROUTE_INITIAL_PASSWORD")"
  omniroute_api_key="$(_json_get_value "${runtime_json}" "OMNIROUTE_API_KEY")"
  omniroute_api_key_name="orchestrathreads-${environment}-runtime"
  omniroute_base_url="http://127.0.0.1:${OT_PORT_OMNIROUTE:-20229}"
  omniroute_write_token=""
  if [[ -n "${writer_role_id_var:-}" && -n "${writer_secret_id_var:-}" ]]; then
    if _require_env "${writer_role_id_var}" >/dev/null 2>&1 && _require_env "${writer_secret_id_var}" >/dev/null 2>&1; then
      omniroute_write_token="$(_vault_login_approle "${writer_role_id_var}" "${writer_secret_id_var}")"
    fi
  fi
  if [[ -z "${omniroute_write_token}" ]]; then
    omniroute_write_token="$(_read_local_root_token)"
  fi

  if [[ "${pull_flag}" == "--pull" ]]; then
    docker compose --env-file "${output_env_file}" pull
  fi
  docker compose --env-file "${output_env_file}" up -d --build orchestra-omniroute orchestra-wet

  omniroute_bootstrap_json="$(bash "${OMNIROUTE_BOOTSTRAP_SCRIPT}" \
    --base-url "${omniroute_base_url}" \
    --initial-password "${omniroute_password}" \
    --api-key-name "${omniroute_api_key_name}" \
    --existing-api-key "${omniroute_api_key}" \
    --vault-addr "${VAULT_ADDR}" \
    --vault-token "${omniroute_write_token}" \
    --vault-path "${VAULT_SECRET_PREFIX}/${environment}/runtime")"
  omniroute_api_key="$(_json_get_value "${omniroute_bootstrap_json}" "api_key")"
  omniroute_bootstrap_status="$(_json_get_value "${omniroute_bootstrap_json}" "status")"
  runtime_json="$(_json_set_value "${runtime_json}" "OMNIROUTE_API_KEY" "${omniroute_api_key}")"
  _render_runtime_env_file "${template_path}" "${runtime_json}" "${output_env_file}"
  chmod 600 "${output_env_file}"

  docker compose --env-file "${output_env_file}" up -d --build

  if [[ "${OT_KEEP_RUNTIME_ENV_FILE:-0}" != "1" ]]; then
    rm -f "${output_env_file}"
  fi

  printf 'Deployed environment %s with project name %s\n' "${environment}" "${project_name}"
  printf 'OmniRoute bootstrap status: %s\n' "${omniroute_bootstrap_status}"
  printf '\n'
  printf '┌─────────────────────────────────────────────────────┐\n'
  printf '│  OmniRoute — connect providers                      │\n'
  printf '├─────────────────────────────────────────────────────┤\n'
  printf '│  URL:      %-40s│\n' "${omniroute_base_url}"
  printf '│  Password: %-40s│\n' "${omniroute_password}"
  printf '│  API key:  %-40s│\n' "${omniroute_api_key_name}"
  printf '└─────────────────────────────────────────────────────┘\n'
  printf '\n'
  if [[ "${OT_KEEP_RUNTIME_ENV_FILE:-0}" == "1" ]]; then
    printf 'Rendered env file kept at: %s\n' "${output_env_file}"
  else
    printf 'Rendered env file removed after deploy\n'
  fi
}

main "$@"
