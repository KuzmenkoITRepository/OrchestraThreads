#!/usr/bin/env bash

if [[ -n "${DEPLOY_LIB_COMMON_LOADED:-}" ]]; then
  return 0
fi

DEPLOY_LIB_COMMON_LOADED=1

# Resolve the MAIN repository root (not a worktree). This ensures all
# control-plane paths (environments/, deploy/vault/local/) resolve correctly
# even when scripts are invoked from inside a worktree.
ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
if [[ -z "${ROOT_DIR}" || ! -d "${ROOT_DIR}/deploy" ]]; then
  # Fallback: assume deploy/lib is two levels below repo root
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi

log_info() {
  local message

  message="${*}"
  printf '[INFO] %s\n' "${message}" >&2
}

log_error() {
  local message

  message="${*}"
  printf '[ERROR] %s\n' "${message}" >&2
}

die() {
  local message

  message="${*}"
  log_error "${message}"
  exit 1
}

validate_env_name() {
  local env_name

  env_name="${1:-}"

  [[ "${env_name}" =~ ^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$ ]]
}

is_protected_env() {
  local env_name

  env_name="${1:-}"

  case "${env_name}" in
    dev | stg | prod)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

check_disk_space() {
  local available_kb
  local minimum_kb

  minimum_kb=2097152
  available_kb="$(df -Pk . | awk 'NR == 2 { print $4 }')"

  if [[ -z "${available_kb}" ]]; then
    log_error 'Unable to determine available disk space'
    return 1
  fi

  if (( available_kb < minimum_kb )); then
    log_error "At least 2GB free space is required on the current partition"
    return 1
  fi
}

get_envs_root() {
  local envs_root

  envs_root="${OT_ENVS_ROOT:-${ROOT_DIR}/environments}"
  printf '%s\n' "${envs_root}"
}

get_repo_root() {
  printf '%s\n' "${ROOT_DIR}"
}

get_agent_compose_runtime_dir() {
  local workspace_dir

  workspace_dir="${1:-}"
  printf '%s\n' "${workspace_dir}/.orchestra_agents_compose"
}

compose_service_name_for_slug() {
  local slug

  slug="${1:-}"
  printf 'agent-%s\n' "${slug//_/-}"
}

remove_env_agent_compose_services() {
  local compose_project_name
  local workspace_dir
  local remove_runtime_dir
  local compose_dir
  local compose_file
  local compose_files
  local service_name
  local slug

  compose_project_name="${1:-}"
  workspace_dir="${2:-}"
  remove_runtime_dir="${3:-0}"
  compose_dir="$(get_agent_compose_runtime_dir "${workspace_dir}")"

  if [[ ! -d "${compose_dir}" ]]; then
    return 0
  fi

  shopt -s nullglob
  compose_files=("${compose_dir}"/*.yaml)
  shopt -u nullglob

  for compose_file in "${compose_files[@]}"; do
    slug="$(basename "${compose_file}" .yaml)"
    service_name="$(compose_service_name_for_slug "${slug}")"
    docker compose -p "${compose_project_name}" -f "${compose_file}" rm -sf "${service_name}" >/dev/null 2>&1 || true
  done

  if [[ "${remove_runtime_dir}" == "1" ]]; then
    rm -rf "${compose_dir}"
  fi
}

require_cmd() {
  local cmd_name

  cmd_name="${1:-}"

  if ! command -v "${cmd_name}" >/dev/null 2>&1; then
    log_error "Required command not found: ${cmd_name}"
    return 1
  fi
}

require_env() {
  local env_name
  local env_value

  env_name="${1:-}"

  if [[ -z "${env_name}" ]]; then
    log_error 'Environment variable name is required'
    return 1
  fi

  if [[ -z "${!env_name:-}" ]]; then
    log_error "Required environment variable not set: ${env_name}"
    return 1
  fi

  env_value="${!env_name}"
  printf '%s\n' "${env_value}"
}
