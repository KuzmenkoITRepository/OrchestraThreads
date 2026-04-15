#!/usr/bin/env bash

if [[ -n "${DEPLOY_LIB_PORT_ALLOCATOR_LOADED:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

port_allocator_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
common_lib_file="${port_allocator_lib_dir}/common.sh"

if [[ ! -f "${common_lib_file}" ]]; then
  printf 'Missing required library: %s\n' "${common_lib_file}" >&2
  return 1 2>/dev/null || exit 1
fi

source "${common_lib_file}"
DEPLOY_LIB_PORT_ALLOCATOR_LOADED=1

_port_allocator_env_dir() {
  local env_name

  env_name="$1"
  printf '%s/%s\n' "${ENVS_ROOT}" "${env_name}"
}

_port_allocator_ports_file() {
  local env_name

  env_name="$1"
  printf '%s/ports.env\n' "$(_port_allocator_env_dir "${env_name}")"
}

_port_allocator_port_keys() {
  printf '%s\n' \
    OT_PORT_THREADS \
    OT_PORT_EVENTS \
    OT_PORT_AGENTS \
    OT_PORT_TASK_REGISTRY \
    OT_PORT_SCHEDULER \
    OT_PORT_LANGFUSE \
    OT_PORT_OMNIROUTE \
    OT_PORT_VAULT
}

_port_allocator_port_values() {
  local base_port

  base_port="$1"
  printf '%s\n' \
    "${base_port}" \
    "$((base_port + 1))" \
    "$((base_port + 2))" \
    "$((base_port + 3))" \
    "$((base_port + 4))" \
    "$((base_port + 5))" \
    "$((base_port + 6))" \
    "$((base_port + 7))" \
    "8200"
}

_port_allocator_validate_env_name() {
  local env_name

  env_name="$1"
  if [[ ! "${env_name}" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    printf 'Invalid environment name: %s\n' "${env_name}" >&2
    return 1
  fi
}

_port_allocator_existing_bases() {
  local ports_file key value existing_base
  local -a ports_files

  shopt -s nullglob
  ports_files=("${ENVS_ROOT}"/*/ports.env)
  shopt -u nullglob

  for ports_file in "${ports_files[@]}"; do
    [[ -f "${ports_file}" ]] || continue
    while IFS='=' read -r key value; do
      if [[ "${key}" == OT_PORT_VAULT ]]; then
        existing_base="${value}"
        if [[ -n "${existing_base}" ]]; then
          printf '%s\n' "${existing_base}"
        fi
        break
      fi
    done < "${ports_file}"
  done
}

is_port_free() {
  local port
  local -a ss_lines

  port="$1"
  mapfile -t ss_lines < <(ss -tl4 "( sport = :${port} )" 2>/dev/null || true)
  (( ${#ss_lines[@]} <= 1 ))
}

find_free_port_range() {
  local base_port offset port candidate_base
  local -a existing_bases

  existing_bases=()
  while IFS= read -r candidate_base; do
    [[ -n "${candidate_base}" ]] || continue
    existing_bases+=("${candidate_base}")
  done < <(_port_allocator_existing_bases)

  for ((base_port = 30000; base_port <= 39990; base_port += 10)); do
    for candidate_base in "${existing_bases[@]}"; do
      if [[ "${candidate_base}" -eq "${base_port}" ]]; then
        continue 2
      fi
    done

    for offset in 0 1 2 3 4 5 6 7 8 9; do
      port="$((base_port + offset))"
      if ! is_port_free "${port}"; then
        continue 2
      fi
    done

    printf '%s\n' "${base_port}"
    return 0
  done

  printf 'No free port range available in 30000-39999\n' >&2
  return 1
}

save_port_allocation() {
  local env_name base_port ports_file key value
  local -a keys values

  env_name="$1"
  base_port="$2"
  ports_file="$(_port_allocator_ports_file "${env_name}")"

  keys=()
  while IFS= read -r key; do
    keys+=("${key}")
  done < <(_port_allocator_port_keys)

  values=()
  while IFS= read -r value; do
    values+=("${value}")
  done < <(_port_allocator_port_values "${base_port}")

  : > "${ports_file}"
  for ((index = 0; index < ${#keys[@]}; index += 1)); do
    printf '%s=%s\n' "${keys[index]}" "${values[index]}" >> "${ports_file}"
  done
}

load_port_allocation() {
  local env_name ports_file key value

  env_name="$1"
  ports_file="$(_port_allocator_ports_file "${env_name}")"

  if [[ ! -f "${ports_file}" ]]; then
    printf 'Port allocation file not found: %s\n' "${ports_file}" >&2
    return 1
  fi

  while IFS='=' read -r key value; do
    case "${key}" in
      OT_PORT_*)
        export "${key}=${value}"
        ;;
    esac
  done < "${ports_file}"
}

release_ports() {
  local env_name ports_file

  env_name="$1"
  ports_file="$(_port_allocator_ports_file "${env_name}")"
  rm -f "${ports_file}"
}

allocate_ports() {
  local env_name env_dir ports_file base_port lock_file

  env_name="$1"
  _port_allocator_validate_env_name "${env_name}"
  env_dir="$(_port_allocator_env_dir "${env_name}")"
  ports_file="$(_port_allocator_ports_file "${env_name}")"
  lock_file="${ENVS_ROOT}/.port-allocator.lock"

  if [[ ! -d "${env_dir}" ]]; then
    printf 'Environment directory does not exist: %s\n' "${env_dir}" >&2
    return 1
  fi

  exec 200>"${lock_file}"
  flock 200

  if [[ -f "${ports_file}" ]]; then
    load_port_allocation "${env_name}"
    exec 200>&-
    return 0
  fi

  base_port="$(find_free_port_range)"
  save_port_allocation "${env_name}" "${base_port}"
  load_port_allocation "${env_name}"
  exec 200>&-
}
