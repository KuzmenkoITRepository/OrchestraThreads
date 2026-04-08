#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/worktree-manager.sh"

: "${VAULT_ADDR:=http://127.0.0.1:8200}"

usage() {
  printf 'Usage: %s <env-name> [--force] [--keep-secrets]\n' "$(basename "$0")" >&2
  exit 1
}

main() {
  local env_name="${1:-}"
  local force_teardown=0
  local keep_secrets=0
  local env_dir
  local workspace_dir
  local ports_file
  local root_token_file
  local compose_project_name
  local agent_prefix
  local agent_container_ids

  if [[ -z "${env_name}" ]]; then
    usage
  fi

  shift || true
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      --force)
        force_teardown=1
        ;;
      --keep-secrets)
        keep_secrets=1
        ;;
      *)
        usage
        ;;
    esac
    shift
  done

  if ! validate_env_name "${env_name}"; then
    die "Invalid environment name: ${env_name}"
  fi

  if is_protected_env "${env_name}" && [[ ${force_teardown} -ne 1 ]]; then
    die "Refusing to tear down protected environment '${env_name}' without --force"
  fi

  env_dir="$(get_envs_root)/${env_name}"
  workspace_dir="${env_dir}/workspace"
  ports_file="${env_dir}/ports.env"
  root_token_file="${ROOT_DIR}/deploy/vault/local/root-token"
  compose_project_name="orchestrathreads-${env_name}"
  agent_prefix="${compose_project_name}-agent-"

  if [[ ! -d "${env_dir}" ]]; then
    die "Environment directory not found: ${env_dir}"
  fi

  if [[ -f "${ports_file}" ]]; then
    set -a
    source "${ports_file}"
    set +a
  fi

  if [[ -d "${workspace_dir}" ]]; then
    export OT_WORKSPACE_DIR="${workspace_dir}"
  fi

  export COMPOSE_PROJECT_NAME="${compose_project_name}"
  docker compose -p "${compose_project_name}" down --volumes --remove-orphans 2>/dev/null || true
  agent_container_ids="$(docker ps -aq --filter "name=${agent_prefix}")"
  if [[ -n "${agent_container_ids}" ]]; then
    docker rm -f ${agent_container_ids} >/dev/null 2>&1 || true
  fi
  docker rm -f "${compose_project_name}-vault-1" 2>/dev/null || true
  docker network rm "${compose_project_name}_default" 2>/dev/null || true

  # Clean root-owned files FIRST (Docker containers may create files as root)
  if [[ -d "${env_dir}" ]]; then
    docker run --rm -v "${env_dir}:/cleanup" alpine:3 sh -c 'find /cleanup -mindepth 1 -delete' 2>/dev/null || true
  fi

  # Remove worktree (git metadata)
  if worktree_exists "${workspace_dir}"; then
    remove_worktree "${workspace_dir}"
  else
    local repo_root
    repo_root="$(get_repo_root)"
    git -C "${repo_root}" worktree unlock "${workspace_dir}" 2>/dev/null || true
    git -C "${repo_root}" worktree remove --force "${workspace_dir}" 2>/dev/null || true
    git -C "${repo_root}" worktree prune 2>/dev/null || true
  fi

  if [[ ${keep_secrets} -ne 1 ]]; then
    if [[ -f "${root_token_file}" ]]; then
      local vault_token

      vault_token="$(<"${root_token_file}")"
      curl -fsS -X DELETE -H "X-Vault-Token: ${vault_token}" "${VAULT_ADDR}/v1/kv/data/orchestrathreads/${env_name}/runtime" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${vault_token}" "${VAULT_ADDR}/v1/kv/metadata/orchestrathreads/${env_name}/runtime" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${vault_token}" "${VAULT_ADDR}/v1/sys/policies/acl/orchestrathreads-${env_name}-runtime-read" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${vault_token}" "${VAULT_ADDR}/v1/sys/policies/acl/orchestrathreads-${env_name}-runtime-write" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${vault_token}" "${VAULT_ADDR}/v1/auth/approle/role/orchestrathreads-${env_name}-runtime" 2>/dev/null || true
      curl -fsS -X DELETE -H "X-Vault-Token: ${vault_token}" "${VAULT_ADDR}/v1/auth/approle/role/orchestrathreads-${env_name}-runtime-writer" 2>/dev/null || true
    else
      log_error "Root token file not found: ${root_token_file}"
    fi

    rm -f "${ROOT_DIR}/deploy/vault/local/${env_name}-approle.env"
  fi

  rm -rf "${env_dir}"

  log_info "Tore down environment '${env_name}'"
  log_info "Removed environment directory: ${env_dir}"
  log_info "Docker project removed: ${compose_project_name}"
  if [[ ${keep_secrets} -eq 1 ]]; then
    log_info 'Vault secrets preserved (--keep-secrets)'
  else
    log_info 'Vault secrets deleted'
  fi
}

main "$@"
