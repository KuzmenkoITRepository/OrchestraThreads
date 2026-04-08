#!/usr/bin/env bash

set -euo pipefail

BASE_URL=""
INITIAL_PASSWORD=""
API_KEY_NAME=""
EXISTING_API_KEY=""
VAULT_ADDR=""
VAULT_TOKEN=""
VAULT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --initial-password)
      INITIAL_PASSWORD="$2"
      shift 2
      ;;
    --api-key-name)
      API_KEY_NAME="$2"
      shift 2
      ;;
    --existing-api-key)
      EXISTING_API_KEY="$2"
      shift 2
      ;;
    --vault-addr)
      VAULT_ADDR="$2"
      shift 2
      ;;
    --vault-token)
      VAULT_TOKEN="$2"
      shift 2
      ;;
    --vault-path)
      VAULT_PATH="$2"
      shift 2
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

BASE_URL="${BASE_URL%/}"
VAULT_ADDR="${VAULT_ADDR%/}"
VAULT_PATH="${VAULT_PATH#/}"
VAULT_PATH="${VAULT_PATH%/}"

for _attempt in $(seq 1 180); do
  if curl -fsS "${BASE_URL}/api/settings/require-login" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${BASE_URL}/api/settings/require-login" >/dev/null 2>&1; then
  printf 'omniroute did not become ready in time\n' >&2
  exit 1
fi

if [[ -n "${EXISTING_API_KEY}" ]]; then
  if curl -fsS -H "Authorization: Bearer ${EXISTING_API_KEY}" "${BASE_URL}/api/keys" >/dev/null 2>&1; then
    jq -cn \
      --arg api_key "${EXISTING_API_KEY}" \
      --arg status "reused_existing_api_key" \
      --arg key_name "${API_KEY_NAME}" \
      '{api_key: $api_key, status: $status, key_name: $key_name, vault_updated: false}'
    exit 0
  fi
fi

cookie_jar="$(mktemp)"
trap 'rm -f "${cookie_jar}"' EXIT

curl -fsS \
  -c "${cookie_jar}" \
  -H 'Content-Type: application/json' \
  -X POST \
  -d "$(jq -cn --arg password "${INITIAL_PASSWORD}" '{password: $password}')" \
  "${BASE_URL}/api/auth/login" >/dev/null

api_key_json="$({
  curl -fsS \
    -b "${cookie_jar}" \
    -H 'Content-Type: application/json' \
    -X POST \
    -d "$(jq -cn --arg name "${API_KEY_NAME}" '{name: $name}')" \
    "${BASE_URL}/api/keys";
} )"
api_key="$(printf '%s' "${api_key_json}" | jq -r '.key')"

if [[ -z "${api_key}" || "${api_key}" == "null" ]]; then
  printf 'failed to create omniroute api key\n' >&2
  exit 1
fi

vault_updated=false
if [[ -n "${VAULT_ADDR}" && -n "${VAULT_TOKEN}" && -n "${VAULT_PATH}" ]]; then
  runtime_json="$(curl -fsS -H "X-Vault-Token: ${VAULT_TOKEN}" "${VAULT_ADDR}/v1/${VAULT_PATH}")"
  updated_payload="$(printf '%s' "${runtime_json}" | jq --arg api_key "${api_key}" '.data.data.OMNIROUTE_API_KEY = $api_key | {data: .data.data}')"
  curl -fsS \
    -H "X-Vault-Token: ${VAULT_TOKEN}" \
    -H 'Content-Type: application/json' \
    -X POST \
    -d "${updated_payload}" \
    "${VAULT_ADDR}/v1/${VAULT_PATH}" >/dev/null
  vault_updated=true
fi

jq -cn \
  --arg api_key "${api_key}" \
  --arg status "created_api_key" \
  --arg key_name "${API_KEY_NAME}" \
  --argjson vault_updated "${vault_updated}" \
  '{api_key: $api_key, status: $status, key_name: $key_name, vault_updated: $vault_updated}'
