#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  printf 'Usage: %s <env-name>\n' "$(basename "$0")" >&2
  exit 1
}

main() {
  local env_name="${1:-}"
  local compose_project_name
  local agent_prefix
  local env_dir
  local workspace_dir
  local container_ids

  if [[ -z "${env_name}" ]]; then
    usage
  fi
  if ! validate_env_name "${env_name}"; then
    die "Invalid environment name: ${env_name}"
  fi

  compose_project_name="orchestrathreads-${env_name}"
  agent_prefix="${compose_project_name}-agent-"
  env_dir="$(get_envs_root)/${env_name}"
  workspace_dir="${env_dir}/workspace"

  if [[ -d "${workspace_dir}" ]]; then
    export OT_WORKSPACE_DIR="${workspace_dir}"
  fi

  docker compose -p "${compose_project_name}" down --remove-orphans 2>/dev/null || true

  container_ids="$(docker ps -aq --filter "name=${agent_prefix}")"
  if [[ -n "${container_ids}" ]]; then
    docker rm -f ${container_ids} >/dev/null
  fi

  docker rm -f "${compose_project_name}-vault-1" 2>/dev/null || true
  docker network rm "${compose_project_name}_default" 2>/dev/null || true

  log_info "Stopped environment '${env_name}'"
}

main "$@"
