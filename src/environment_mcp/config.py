from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_VAULT_ADDR = "http://127.0.0.1:8200"


@dataclass(frozen=True)
class EnvironmentMCPConfig:
    repo_root: Path
    deploy_dir: Path
    envs_root: Path
    vault_addr: str


def load_config() -> EnvironmentMCPConfig:
    repo_root = _repo_root()
    deploy_dir = repo_root / "deploy"
    if not deploy_dir.is_dir():
        raise RuntimeError(f"Deploy directory not found: {deploy_dir}")
    envs_root = Path(os.getenv("OT_ENVS_ROOT") or repo_root / "environments").resolve()
    return EnvironmentMCPConfig(
        repo_root=repo_root,
        deploy_dir=deploy_dir,
        envs_root=envs_root,
        vault_addr=os.getenv("VAULT_ADDR", _DEFAULT_VAULT_ADDR).rstrip("/"),
    )


def _repo_root() -> Path:
    configured = os.getenv("ENVIRONMENT_MCP_REPO_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[2]
