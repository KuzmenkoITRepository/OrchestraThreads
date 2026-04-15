from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from environment_mcp.config import EnvironmentMCPConfig

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class EnvironmentPaths:
    name: str
    env_dir: Path
    workspace_dir: Path
    runtime_dir: Path
    approle_file: Path
    ports_file: Path


def enrich_environment_rows(
    config: EnvironmentMCPConfig,
    rows: list[JsonDict],
) -> list[JsonDict]:
    return _EnvironmentState.enrich_rows(config, rows)


def environment_payload(
    config: EnvironmentMCPConfig,
    name: str,
    *,
    status: str | None = None,
    has_workspace: bool | None = None,
) -> JsonDict:
    return _EnvironmentState.payload(
        config,
        name,
        status=status,
        has_workspace=has_workspace,
    )


class _EnvironmentState:
    protected_environments = frozenset(("dev", "stg", "prod"))

    @classmethod
    def enrich_rows(
        cls,
        config: EnvironmentMCPConfig,
        rows: list[JsonDict],
    ) -> list[JsonDict]:
        enriched: list[JsonDict] = []
        for row in rows:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            enriched.append(
                cls.payload(
                    config,
                    name,
                    status=str(row.get("status") or "stopped"),
                    has_workspace=cls._workspace_flag(row.get("has_workspace")),
                ),
            )
        return enriched

    @classmethod
    def payload(
        cls,
        config: EnvironmentMCPConfig,
        name: str,
        *,
        status: str | None,
        has_workspace: bool | None,
    ) -> JsonDict:
        paths = cls._paths(config, name)
        ports = cls._read_kv_file(paths.ports_file)
        workspace_exists = has_workspace
        if workspace_exists is None:
            workspace_exists = paths.workspace_dir.is_dir()
        resolved_status = status
        if resolved_status is None:
            resolved_status = "stopped" if paths.env_dir.is_dir() else "missing"
        return {
            "name": name,
            "status": resolved_status,
            "protected": name in cls.protected_environments,
            "vault_path": f"kv/orchestrathreads/{name}/runtime",
            "vault_addr": config.vault_addr,
            "environment_dir": str(paths.env_dir),
            "workspace_dir": str(paths.workspace_dir),
            "workspace_exists": workspace_exists,
            "runtime_dir": str(paths.runtime_dir),
            "approle_file": str(paths.approle_file),
            "approle_exists": paths.approle_file.is_file(),
            "ports": ports,
            "urls": cls._urls(ports),
        }

    @staticmethod
    def _paths(config: EnvironmentMCPConfig, name: str) -> EnvironmentPaths:
        env_dir = config.envs_root / name
        return EnvironmentPaths(
            name=name,
            env_dir=env_dir,
            workspace_dir=env_dir / "workspace",
            runtime_dir=env_dir / "runtime",
            approle_file=env_dir / "approle.env",
            ports_file=env_dir / "ports.env",
        )

    @staticmethod
    def _read_kv_file(path: Path) -> dict[str, str]:
        if not path.is_file():
            return {}
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    @classmethod
    def _urls(cls, ports: dict[str, str]) -> dict[str, str]:
        return {
            "threads": cls._http_url(ports.get("OT_PORT_THREADS")),
            "events": cls._http_url(ports.get("OT_PORT_EVENTS")),
            "agents": cls._http_url(ports.get("OT_PORT_AGENTS")),
            "task_registry": cls._http_url(ports.get("OT_PORT_TASK_REGISTRY")),
            "scheduler": cls._http_url(ports.get("OT_PORT_SCHEDULER")),
            "langfuse": cls._http_url(ports.get("OT_PORT_LANGFUSE")),
            "omniroute": cls._http_url(ports.get("OT_PORT_OMNIROUTE")),
            "vault": cls._http_url(ports.get("OT_PORT_VAULT")),
        }

    @staticmethod
    def _http_url(port: str | None) -> str:
        normalized = str(port or "").strip()
        return f"http://127.0.0.1:{normalized}" if normalized else ""

    @staticmethod
    def _workspace_flag(value: object) -> bool | None:
        normalized = str(value or "").strip().lower()
        if normalized:
            return normalized in {"1", "true", "yes"}
        return None
