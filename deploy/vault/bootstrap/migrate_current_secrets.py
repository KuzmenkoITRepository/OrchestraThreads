from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


class _MigrationContext:
    def __init__(
        self,
        *,
        vault_addr: str,
        vault_token: str,
        payloads: dict[str, dict[str, str]],
    ) -> None:
        self.vault_addr = vault_addr
        self.vault_token = vault_token
        self.payloads = payloads


class _RuntimeSecretBuilder:
    runtime_keys: tuple[str, ...] = (
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "ORCHESTRA_THREADS_DATABASE_URL",
        "ORCHESTRA_THREADS_DB_SCHEMA",
        "ORCHESTRA_THREADS_DB_MIN_POOL_SIZE",
        "ORCHESTRA_THREADS_DB_MAX_POOL_SIZE",
        "ORCHESTRA_THREADS_HOST",
        "ORCHESTRA_THREADS_PORT",
        "TASK_REGISTRY_HOST",
        "TASK_REGISTRY_PORT",
        "TASK_REGISTRY_DATABASE_URL",
        "SCHEDULER_CRON_HOST",
        "SCHEDULER_CRON_PORT",
        "SCHEDULER_CRON_DATABASE_URL",
        "SCHEDULER_CRON_DB_SCHEMA",
        "LANGFUSE_DB_NAME",
        "LANGFUSE_DB_USER",
        "LANGFUSE_DB_PASSWORD",
        "LANGFUSE_NEXTAUTH_URL",
        "LANGFUSE_NEXTAUTH_SECRET",
        "LANGFUSE_SALT",
        "LANGFUSE_TELEMETRY_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        "OMNIROUTE_INITIAL_PASSWORD",
        "OMNIROUTE_API_KEY",
        "OT_PORT_THREADS",
        "OT_PORT_EVENTS",
        "OT_PORT_AGENTS",
        "OT_PORT_TASK_REGISTRY",
        "OT_PORT_SCHEDULER",
        "OT_PORT_LANGFUSE",
        "OT_PORT_OMNIROUTE",
        "OT_PORT_VAULT",
        "OT_OMNIROUTE_DATA_DIR",
        "OT_SESSIONS_DIR",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
        "TELEGRAM_CHAT_ID_IVAN",
        "LOG_LEVEL",
    )
    env_paths: tuple[str, ...] = (".env", ".env.telegram")
    environments: tuple[str, ...] = ("prod", "dev", "stg")
    default_items: tuple[tuple[str, str], ...] = (
        ("POSTGRES_DB", "orchestra_threads"),
        ("POSTGRES_USER", "orchestra"),
        ("POSTGRES_PASSWORD", "orchestra"),
        (
            "ORCHESTRA_THREADS_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
        ("ORCHESTRA_THREADS_DB_SCHEMA", "public"),
        ("ORCHESTRA_THREADS_DB_MIN_POOL_SIZE", "5"),
        ("ORCHESTRA_THREADS_DB_MAX_POOL_SIZE", "20"),
        ("ORCHESTRA_THREADS_HOST", "0.0.0.0"),
        ("ORCHESTRA_THREADS_PORT", "8788"),
        ("TASK_REGISTRY_HOST", "0.0.0.0"),
        ("TASK_REGISTRY_PORT", "8791"),
        (
            "TASK_REGISTRY_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
        ("SCHEDULER_CRON_HOST", "0.0.0.0"),
        ("SCHEDULER_CRON_PORT", "8792"),
        (
            "SCHEDULER_CRON_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
        ("SCHEDULER_CRON_DB_SCHEMA", "public"),
        ("LANGFUSE_DB_NAME", "langfuse"),
        ("LANGFUSE_DB_USER", "langfuse"),
        ("LANGFUSE_DB_PASSWORD", "langfuse"),
        ("LANGFUSE_NEXTAUTH_URL", "http://localhost:3000"),
        ("LANGFUSE_NEXTAUTH_SECRET", ""),
        ("LANGFUSE_SALT", ""),
        ("LANGFUSE_TELEMETRY_ENABLED", "false"),
        ("LANGFUSE_PUBLIC_KEY", ""),
        ("LANGFUSE_SECRET_KEY", ""),
        ("LANGFUSE_BASE_URL", ""),
        ("OMNIROUTE_INITIAL_PASSWORD", ""),
        ("OMNIROUTE_API_KEY", ""),
        ("OT_PORT_THREADS", "8788"),
        ("OT_PORT_EVENTS", "8789"),
        ("OT_PORT_AGENTS", "8790"),
        ("OT_PORT_TASK_REGISTRY", "8791"),
        ("OT_PORT_SCHEDULER", "8792"),
        ("OT_PORT_LANGFUSE", "3000"),
        ("OT_PORT_OMNIROUTE", "20229"),
        ("OT_PORT_VAULT", "8200"),
        ("OT_OMNIROUTE_DATA_DIR", "./runtime_state/orchestrathreads/omniroute-data"),
        ("OT_SESSIONS_DIR", "./runtime_state/orchestrathreads/sessions"),
        ("TELEGRAM_API_ID", ""),
        ("TELEGRAM_API_HASH", ""),
        ("TELEGRAM_SESSION_STRING", ""),
        ("TELEGRAM_CHAT_ID_IVAN", "748976004"),
        ("LOG_LEVEL", "INFO"),
    )
    non_prod_empty_keys: tuple[str, ...] = (
        "OMNIROUTE_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
    )

    def build_all(self, base_dir: Path) -> dict[str, dict[str, str]]:
        runtime_values = self._runtime_values(base_dir)
        return {
            environment: self._environment_payload(runtime_values, environment)
            for environment in self.environments
        }

    def _runtime_values(self, base_dir: Path) -> dict[str, str]:
        current = dict(self.default_items)
        for relative_path in self.env_paths:
            current.update(self._read_env_file(base_dir / relative_path))
        return {key: current[key] if key in current else "" for key in self.runtime_keys}

    def _read_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _environment_payload(
        self,
        runtime_values: dict[str, str],
        environment: str,
    ) -> dict[str, str]:
        payload = dict(runtime_values)
        offset = self._offset(environment)
        payload["OT_PORT_THREADS"] = str(8788 + offset)
        payload["OT_PORT_EVENTS"] = str(8789 + offset)
        payload["OT_PORT_AGENTS"] = str(8790 + offset)
        payload["OT_PORT_TASK_REGISTRY"] = str(8791 + offset)
        payload["OT_PORT_SCHEDULER"] = str(8792 + offset)
        payload["OT_PORT_LANGFUSE"] = str(3000 + offset)
        payload["OT_PORT_OMNIROUTE"] = str(20229 + offset)
        payload["OT_PORT_VAULT"] = "8200"
        payload["OT_OMNIROUTE_DATA_DIR"] = (
            f"./runtime_state/orchestrathreads-{environment}/omniroute-data"
        )
        payload["OT_SESSIONS_DIR"] = f"./runtime_state/orchestrathreads-{environment}/sessions"
        if environment != "prod":
            payload.update(self._secret_values(environment))
            database_url = (
                f"postgresql://orchestra:{payload['POSTGRES_PASSWORD']}"
                "@postgres:5432/orchestra_threads"
            )
            payload["ORCHESTRA_THREADS_DATABASE_URL"] = database_url
            payload["TASK_REGISTRY_DATABASE_URL"] = database_url
            payload["SCHEDULER_CRON_DATABASE_URL"] = database_url
        return payload

    def _offset(self, environment: str) -> int:
        if environment == "dev":
            return 0
        if environment == "stg":
            return 100
        return 200

    def _secret_values(self, environment: str) -> dict[str, str]:
        values = {
            "POSTGRES_PASSWORD": f"orchestra-{environment}-{secrets.token_hex(8)}",
            "LANGFUSE_DB_PASSWORD": f"langfuse-{environment}-{secrets.token_hex(8)}",
            "LANGFUSE_NEXTAUTH_SECRET": secrets.token_urlsafe(32),
            "LANGFUSE_SALT": secrets.token_urlsafe(24),
            "OMNIROUTE_INITIAL_PASSWORD": secrets.token_urlsafe(24),
        }
        for key in self.non_prod_empty_keys:
            values[key] = ""
        return values


def _vault_request(
    *,
    url: str,
    method: str,
    token: str,
    payload: dict[str, object],
) -> None:
    request = urlrequest.Request(
        url=url,
        method=method,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Vault-Token": token,
        },
    )
    with urlrequest.urlopen(request, timeout=30):
        return


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise ValueError(f"missing required environment variable: {name}")


def _migration_context() -> _MigrationContext:
    return _MigrationContext(
        vault_addr=_required_env("VAULT_ADDR").rstrip("/"),
        vault_token=_required_env("VAULT_TOKEN"),
        payloads=_RuntimeSecretBuilder().build_all(Path(__file__).resolve().parents[3]),
    )


def _run_migration() -> None:
    context = _migration_context()
    for environment, values in context.payloads.items():
        _vault_request(
            url=f"{context.vault_addr}/v1/kv/data/orchestrathreads/{environment}/runtime",
            method="POST",
            token=context.vault_token,
            payload={"data": values},
        )
        sys.stdout.write(f"wrote kv/orchestrathreads/{environment}/runtime\n")


def main() -> int:
    try:
        _run_migration()
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    except urlerror.URLError as error:
        sys.stderr.write(f"vault request failed: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
