from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType

import yaml

_AGENTS_ROOT = Path("agents")
_TEMPLATES_ROOT = Path("src/core/orchestra_agents/templates")
_PYTHON_MODULE_COMMAND = ("python", "-m")
_AGENT_MANIFEST_MODULES = MappingProxyType(
    {
        "dev": "core.orchestra_agents.backends.opencode.main",
        "devops": "core.orchestra_agents.backends.opencode.main",
        "opencode-example": "core.orchestra_agents.backends.opencode.main",
        "orchestra": "core.orchestra_agents.backends.agent_mux.main",
        "qa": "core.orchestra_agents.backends.opencode.main",
        "secretary": "core.orchestra_agents.backends.sgr.main",
        "sgr": "core.orchestra_agents.backends.sgr.main",
        "whiner": "core.orchestra_agents.backends.opencode.main",
    }
)
_TEMPLATE_MANIFEST_MODULES = MappingProxyType(
    {
        "agent": "core.orchestra_agents.backends.example.main",
        "agent_mux": "core.orchestra_agents.backends.agent_mux.main",
        "opencode": "core.orchestra_agents.backends.opencode.main",
    }
)
_DIRECT_SRC_PYTHONPATH = "/workspace/src"
_AGENT_ENV_PYTHONPATHS = MappingProxyType(
    {
        "dev": _DIRECT_SRC_PYTHONPATH,
        "devops": _DIRECT_SRC_PYTHONPATH,
        "opencode-example": _DIRECT_SRC_PYTHONPATH,
        "orchestra": _DIRECT_SRC_PYTHONPATH,
        "qa": _DIRECT_SRC_PYTHONPATH,
        "secretary": "/workspace/src:/workspace",
        "sgr": "/workspace/src:/workspace",
        "whiner": _DIRECT_SRC_PYTHONPATH,
    }
)


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _runtime_command(manifest_path: Path) -> list[str]:
    runtime = _load_manifest(manifest_path)["runtime"]
    assert isinstance(runtime, dict)
    command = runtime["command"]
    assert isinstance(command, list)
    return [str(part) for part in command]


def _runtime_env(manifest_path: Path) -> dict[str, str]:
    runtime = _load_manifest(manifest_path)["runtime"]
    assert isinstance(runtime, dict)
    env = runtime["env"]
    assert isinstance(env, dict)
    return {str(key): str(value) for key, value in env.items()}


class AgentLayoutTests(unittest.TestCase):
    def test_agents_tree_has_no_runtime_directories(self) -> None:
        runtime_dirs = sorted(_AGENTS_ROOT.glob("*/agent_runtime"))
        self.assertFalse(runtime_dirs, f"backend runtime dirs remain under agents/: {runtime_dirs}")

    def test_agent_manifests_use_entrypoints(self) -> None:
        for slug, module_name in _AGENT_MANIFEST_MODULES.items():
            with self.subTest(slug=slug):
                command = _runtime_command(_AGENTS_ROOT / slug / "manifest.yaml")
                self.assertEqual(command, [*_PYTHON_MODULE_COMMAND, module_name])

    def test_agent_manifests_use_expected_pythonpath(self) -> None:
        for slug, pythonpath in _AGENT_ENV_PYTHONPATHS.items():
            with self.subTest(slug=slug):
                env = _runtime_env(_AGENTS_ROOT / slug / "manifest.yaml")
                self.assertEqual(env["PYTHONPATH"], pythonpath)

    def test_template_manifests_use_entrypoints(self) -> None:
        for template_name, module_name in _TEMPLATE_MANIFEST_MODULES.items():
            with self.subTest(template=template_name):
                command = _runtime_command(_TEMPLATES_ROOT / template_name / "manifest.yaml")
                self.assertEqual(command, [*_PYTHON_MODULE_COMMAND, module_name])

    def test_backend_templates_use_src_pythonpath(self) -> None:
        for template_name in ("agent_mux", "opencode"):
            with self.subTest(template=template_name):
                env = _runtime_env(_TEMPLATES_ROOT / template_name / "manifest.yaml")
                self.assertEqual(env["PYTHONPATH"], _DIRECT_SRC_PYTHONPATH)
