from __future__ import annotations

import os
import pathlib
import stat
import sys
import tempfile
import unittest
from dataclasses import dataclass
from typing import Any, cast

from core.orchestra_agents import scaffold as scaffold_module
from core.orchestra_agents.tests.template_helpers.fake_agent_mux import (
    _fake_agent_mux_script,
    _load_backend_module,
)

_AGENT_DIR_KEY = "agent_dir"


@dataclass(frozen=True)
class TemplateFixture:
    root: pathlib.Path
    agent_dir: pathlib.Path
    capture_path: pathlib.Path
    agent_mux_binary: pathlib.Path
    backend_module: Any
    backend_class: Any


def _prepare_paths(root: pathlib.Path) -> dict[str, pathlib.Path]:
    agent_dir = root / "generic_worker"
    scaffold_module.scaffold_agent(
        slug="generic_worker",
        output_dir=agent_dir,
        options=scaffold_module.ScaffoldOptions(
            display_name="Generic Worker",
            backend_type="agent_mux",
            template="agent_mux",
        ),
    )
    capture_path = root / "agent-mux-capture.json"
    agent_mux_binary = root / "fake-agent-mux"
    agent_mux_binary.write_text(_fake_agent_mux_script(), encoding="utf-8")
    agent_mux_binary.chmod(agent_mux_binary.stat().st_mode | stat.S_IXUSR)
    return {
        _AGENT_DIR_KEY: agent_dir,
        "capture_path": capture_path,
        "agent_mux_binary": agent_mux_binary,
    }


def build_template_fixture(test_case: unittest.IsolatedAsyncioTestCase) -> TemplateFixture:
    previous_env = _snapshot_env()
    temp_dir = tempfile.TemporaryDirectory()
    root = pathlib.Path(temp_dir.name)
    paths = _prepare_paths(root)

    test_case.addCleanup(temp_dir.cleanup)
    test_case.addCleanup(_restore_env, previous_env)
    test_case.addCleanup(_remove_sys_path_entry, str(paths[_AGENT_DIR_KEY]))
    test_case.addCleanup(_purge_agent_runtime_modules)

    os.environ["FAKE_AGENT_MUX_CAPTURE_PATH"] = str(paths["capture_path"])
    os.environ["PYTHONPATH"] = f"/workspace/src:{paths[_AGENT_DIR_KEY]}"

    _purge_agent_runtime_modules()
    sys.path.insert(0, str(paths[_AGENT_DIR_KEY]))
    backend_module = cast(Any, _load_backend_module())
    return TemplateFixture(
        root=root,
        agent_dir=paths[_AGENT_DIR_KEY],
        capture_path=paths["capture_path"],
        agent_mux_binary=paths["agent_mux_binary"],
        backend_module=backend_module,
        backend_class=cast(Any, backend_module.AgentMuxBackend),
    )


def _purge_agent_runtime_modules() -> None:
    for name in list(sys.modules):
        if name == "agent_runtime" or name.startswith("agent_runtime."):
            sys.modules.pop(name, None)


def _snapshot_env() -> dict[str, str | None]:
    return {
        "FAKE_AGENT_MUX_MODE": os.environ.get("FAKE_AGENT_MUX_MODE"),
        "FAKE_AGENT_MUX_SLEEP": os.environ.get("FAKE_AGENT_MUX_SLEEP"),
        "FAKE_AGENT_MUX_CAPTURE_PATH": os.environ.get("FAKE_AGENT_MUX_CAPTURE_PATH"),
        "PYTHONPATH": os.environ.get("PYTHONPATH"),
    }


def _restore_env(previous_env: dict[str, str | None]) -> None:
    for key, env_value in previous_env.items():
        if env_value is None:
            os.environ.pop(key, None)
            continue
        os.environ[key] = env_value


def _remove_sys_path_entry(entry: str) -> None:
    import contextlib

    with contextlib.suppress(ValueError):
        sys.path.remove(entry)
