#!/usr/bin/env bash

set -euo pipefail

# Source common.sh for git-aware ROOT_DIR resolution (works from worktrees too)
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
LOCAL_DIR="${ROOT_DIR}/deploy/vault/local"

_usage() {
  printf 'Usage: %s <environment> [base-environment]\n' "$(basename "$0")" >&2
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

_ensure_env_name() {
  local environment="$1"
  if [[ ! "${environment}" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    printf 'Invalid environment name: %s\n' "${environment}" >&2
    exit 1
  fi
}

main() {
  local environment="${1:-}"
  local base_environment="${2:-dev}"
  local root_token

  if [[ -z "${environment}" ]]; then
    _usage
  fi
  _ensure_env_name "${environment}"
  _ensure_env_name "${base_environment}"
  _require_cmd python3
  : "${VAULT_ADDR:=http://127.0.0.1:8200}"
  _require_env VAULT_ADDR

  root_token="$(cat "${LOCAL_DIR}/root-token")"

  python3 - "${environment}" "${base_environment}" "${VAULT_ADDR}" "${root_token}" "${LOCAL_DIR}" <<'PY'
from __future__ import annotations

import json
import secrets
import sys
import urllib.request
from pathlib import Path


def vault_request(url: str, *, token: str, method: str = 'GET', payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None
    headers = {'X-Vault-Token': token}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode('utf-8').strip()
    return json.loads(raw) if raw else {}


environment = sys.argv[1]
base_environment = sys.argv[2]
vault_addr = sys.argv[3].rstrip('/')
root_token = sys.argv[4]
local_dir = Path(sys.argv[5])

base_data = vault_request(
    f'{vault_addr}/v1/kv/data/orchestrathreads/{base_environment}/runtime',
    token=root_token,
)['data']['data']

payload = dict(base_data)
payload['OT_OMNIROUTE_DATA_DIR'] = f'./runtime_state/orchestrathreads-{environment}/omniroute-data'
payload['OT_SESSIONS_DIR'] = f'./runtime_state/orchestrathreads-{environment}/sessions'
payload['POSTGRES_PASSWORD'] = f'pg-{environment}-{secrets.token_hex(8)}'
payload['LANGFUSE_DB_PASSWORD'] = f'lf-{environment}-{secrets.token_hex(8)}'
payload['LANGFUSE_NEXTAUTH_SECRET'] = secrets.token_urlsafe(32)
payload['LANGFUSE_SALT'] = secrets.token_urlsafe(24)
payload['OMNIROUTE_INITIAL_PASSWORD'] = secrets.token_urlsafe(24)
payload['OMNIROUTE_API_KEY'] = ''
payload['LANGFUSE_PUBLIC_KEY'] = ''
payload['LANGFUSE_SECRET_KEY'] = ''
payload['ORCHESTRA_THREADS_DATABASE_URL'] = (
    f"postgresql://orchestra:{payload['POSTGRES_PASSWORD']}@postgres:5432/orchestra_threads"
)
payload['TASK_REGISTRY_DATABASE_URL'] = payload['ORCHESTRA_THREADS_DATABASE_URL']
payload['SCHEDULER_CRON_DATABASE_URL'] = payload['ORCHESTRA_THREADS_DATABASE_URL']
for key in (
    'OT_PORT_THREADS',
    'OT_PORT_EVENTS',
    'OT_PORT_AGENTS',
    'OT_PORT_TASK_REGISTRY',
    'OT_PORT_SCHEDULER',
    'OT_PORT_LANGFUSE',
    'OT_PORT_OMNIROUTE',
):
    payload[key] = ''

vault_request(
    f'{vault_addr}/v1/kv/data/orchestrathreads/{environment}/runtime',
    token=root_token,
    method='POST',
    payload={'data': payload},
)

policy = (
    f'path "kv/data/orchestrathreads/{environment}/runtime" {{\n'
    '  capabilities = ["read"]\n'
    '}\n'
    f'path "kv/metadata/orchestrathreads/{environment}/runtime" {{\n'
    '  capabilities = ["read"]\n'
    '}\n'
)
writer_policy = (
    f'path "kv/data/orchestrathreads/{environment}/runtime" {{\n'
    '  capabilities = ["read", "update"]\n'
    '}\n'
    f'path "kv/metadata/orchestrathreads/{environment}/runtime" {{\n'
    '  capabilities = ["read"]\n'
    '}\n'
)
vault_request(
    f'{vault_addr}/v1/sys/policies/acl/orchestrathreads-{environment}-runtime-read',
    token=root_token,
    method='PUT',
    payload={'policy': policy},
)
vault_request(
    f'{vault_addr}/v1/sys/policies/acl/orchestrathreads-{environment}-runtime-write',
    token=root_token,
    method='PUT',
    payload={'policy': writer_policy},
)
vault_request(
    f'{vault_addr}/v1/auth/approle/role/orchestrathreads-{environment}-runtime',
    token=root_token,
    method='POST',
    payload={
        'token_policies': [f'orchestrathreads-{environment}-runtime-read'],
        'token_ttl': '1h',
        'token_max_ttl': '4h',
        'secret_id_ttl': '720h',
        'secret_id_num_uses': 0,
    },
)
vault_request(
    f'{vault_addr}/v1/auth/approle/role/orchestrathreads-{environment}-runtime-writer',
    token=root_token,
    method='POST',
    payload={
        'token_policies': [f'orchestrathreads-{environment}-runtime-write'],
        'token_ttl': '15m',
        'token_max_ttl': '1h',
        'secret_id_ttl': '720h',
        'secret_id_num_uses': 0,
    },
)
role_data = vault_request(
    f'{vault_addr}/v1/auth/approle/role/orchestrathreads-{environment}-runtime/role-id',
    token=root_token,
)
writer_role_data = vault_request(
    f'{vault_addr}/v1/auth/approle/role/orchestrathreads-{environment}-runtime-writer/role-id',
    token=root_token,
)
secret_data = vault_request(
    f'{vault_addr}/v1/auth/approle/role/orchestrathreads-{environment}-runtime/secret-id',
    token=root_token,
    method='POST',
    payload={},
)
writer_secret_data = vault_request(
    f'{vault_addr}/v1/auth/approle/role/orchestrathreads-{environment}-runtime-writer/secret-id',
    token=root_token,
    method='POST',
    payload={},
)
approle_path = local_dir / f'{environment}-approle.env'
approle_path.write_text(
    '\n'.join(
        (
            f'VAULT_ROLE_NAME_{environment.upper().replace("-", "_")}=orchestrathreads-{environment}-runtime',
            f'VAULT_ROLE_ID_{environment.upper().replace("-", "_")}={role_data["data"]["role_id"]}',
            f'VAULT_SECRET_ID_{environment.upper().replace("-", "_")}={secret_data["data"]["secret_id"]}',
            f'VAULT_WRITER_ROLE_NAME_{environment.upper().replace("-", "_")}=orchestrathreads-{environment}-runtime-writer',
            f'VAULT_WRITER_ROLE_ID_{environment.upper().replace("-", "_")}={writer_role_data["data"]["role_id"]}',
            f'VAULT_WRITER_SECRET_ID_{environment.upper().replace("-", "_")}={writer_secret_data["data"]["secret_id"]}',
            '',
        )
    ),
    encoding='utf-8',
)
print(approle_path)
PY
}

main "$@"
