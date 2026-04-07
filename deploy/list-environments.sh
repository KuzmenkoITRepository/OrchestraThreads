#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

json=false
[[ "${1:-}" == "--json" ]] && json=true

ENVS_ROOT="$(get_envs_root)"
shopt -s nullglob
env_dirs=("${ENVS_ROOT}"/*/)

get_port_threads() {
  local file="$1/ports.env" line
  [[ -f "${file}" ]] || { printf 'N/A'; return; }
  line="$(grep -E '^OT_PORT_THREADS=' "${file}" | head -n1 || true)"
  [[ -n "${line}" ]] && printf '%s' "${line#OT_PORT_THREADS=}" || printf 'N/A'
}

json_escape() {
  local value="${1:-}"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "${value}"
}

get_status() {
  local name="$1" output
  output="$(docker compose -p "orchestrathreads-${name}" ps --format json 2>/dev/null || true)"
  [[ "${output}" == *'"running"'* ]] && printf 'running' || printf 'stopped'
}

rows=()
for dir in "${env_dirs[@]}"; do
  name="${dir%/}"; name="${name##*/}"
  status="$(get_status "${name}")"
  port_threads="$(get_port_threads "${dir%/}")"
  has_workspace='no'; [[ -d "${dir}/workspace" ]] && has_workspace='yes'
  rows+=("${name}" "${status}" "${port_threads}" "${has_workspace}")
done

if (( ${#rows[@]} == 0 )); then printf 'No environments found.\n'; exit 0; fi
if ${json}; then
  printf '['; sep=''
  for ((i=0; i<${#rows[@]}; i+=4)); do printf '%s{"name":"%s","status":"%s","port_threads":"%s","has_workspace":"%s"}' "${sep}" "$(json_escape "${rows[i]}")" "$(json_escape "${rows[i+1]}")" "$(json_escape "${rows[i+2]}")" "$(json_escape "${rows[i+3]}")"; sep=','; done
  printf ']\n'; exit 0
fi

printf '%-20s %-8s %-12s %-12s\n' NAME STATUS PORT_THREADS WORKSPACE
for ((i=0; i<${#rows[@]}; i+=4)); do printf '%-20s %-8s %-12s %-12s\n' "${rows[i]}" "${rows[i+1]}" "${rows[i+2]}" "${rows[i+3]}"; done
