#!/usr/bin/env bash

if [[ -n "${DEPLOY_LIB_WORKTREE_MANAGER_LOADED:-}" ]]; then
  return 0
fi

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

DEPLOY_LIB_WORKTREE_MANAGER_LOADED=1

create_worktree() {
  local worktree_path
  local repo_root

  worktree_path="${1:-}"
  repo_root="$(get_repo_root)"

  if [[ -z "${worktree_path}" ]]; then
    return 1
  fi

  if ! git -C "${repo_root}" worktree add --detach "${worktree_path}"; then
    return 1
  fi

  if ! git -C "${repo_root}" worktree lock "${worktree_path}" --reason "Environment workspace"; then
    return 1
  fi

  return 0
}

update_worktree() {
  local worktree_path
  local target_ref

  worktree_path="${1:-}"
  target_ref="${2:-}"

  if [[ -z "${worktree_path}" || -z "${target_ref}" ]]; then
    return 1
  fi

  if ! git -C "${worktree_path}" checkout --detach "${target_ref}" 2>&1; then
    return 1
  fi

  return 0
}

remove_worktree() {
  local worktree_path
  local repo_root
  local tier_one_failed
  local tier_two_failed

  worktree_path="${1:-}"
  repo_root="$(get_repo_root)"
  tier_one_failed=0
  tier_two_failed=0

  if [[ -z "${worktree_path}" ]]; then
    return 0
  fi

  git -C "${repo_root}" worktree unlock "${worktree_path}" 2>/dev/null
  git -C "${repo_root}" worktree remove "${worktree_path}" 2>/dev/null || tier_one_failed=1

  if [[ ${tier_one_failed} -ne 0 ]]; then
    git -C "${repo_root}" worktree remove --force "${worktree_path}" 2>/dev/null || tier_two_failed=1
  fi

  if [[ ${tier_one_failed} -ne 0 && ${tier_two_failed} -ne 0 ]]; then
    rm -rf "${worktree_path}"
    git -C "${repo_root}" worktree prune
  fi

  return 0
}

worktree_exists() {
  local worktree_path
  local repo_root
  local found
  local line

  worktree_path="${1:-}"
  repo_root="$(get_repo_root)"
  found=1

  if [[ -z "${worktree_path}" ]]; then
    return 1
  fi

  while IFS= read -r line; do
    if [[ "${line}" == "worktree ${worktree_path}" ]]; then
      found=0
      break
    fi
  done < <(git -C "${repo_root}" worktree list --porcelain)

  return "${found}"
}
