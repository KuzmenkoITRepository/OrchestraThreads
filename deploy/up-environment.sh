#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  printf 'Usage: %s <env-name> [base-env]\n' "$(basename "$0")" >&2
  exit 1
}

main() {
  local env_name="${1:-}"
  local base_env="${2:-dev}"
  local env_dir

  if [[ -z "${env_name}" ]]; then
    usage
  fi
  if ! validate_env_name "${env_name}"; then
    die "Invalid environment name: ${env_name}"
  fi

  env_dir="$(get_envs_root)/${env_name}"
  if [[ -d "${env_dir}" ]]; then
    bash "${ROOT_DIR}/deploy/deploy-env.sh" "${env_name}"
    return
  fi

  bash "${ROOT_DIR}/deploy/provision-environment.sh" "${env_name}" "${base_env}"
}

main "$@"
