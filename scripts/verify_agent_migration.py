"""Verify or write backend-manifest migration output."""

from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import util as importlib_util
from pathlib import Path
from typing import cast


def _bootstrap_src_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


_bootstrap_src_path()


def _load_run_cli() -> Callable[[], int]:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "core"
        / "orchestra_agents"
        / "_migration_verify_cli.py"
    )
    spec = importlib_util.spec_from_file_location("migration_verify_cli", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_cli = module.run_cli
    assert callable(run_cli)
    return cast(Callable[[], int], run_cli)


run_cli = _load_run_cli()


if __name__ == "__main__":
    sys.exit(run_cli())
