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
