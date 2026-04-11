from __future__ import annotations

import unittest
from importlib import util
from importlib.machinery import ModuleSpec
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_PATHS = (
    _ROOT / "src/core/orchestra_agents/backends/example",
    _ROOT / "src/core/orchestra_agents/backends/example/runtime",
    _ROOT / "src/core/orchestra_agents/backends/sgr",
    _ROOT / "src/core/orchestra_agents/backends/agent_mux",
    _ROOT / "src/core/orchestra_agents/backends/agent_mux/internal",
    _ROOT / "src/core/orchestra_agents/backends/opencode",
)
_TEMPLATE_PATHS = (
    _ROOT / "src/core/orchestra_agents/templates/agent",
    _ROOT / "src/core/orchestra_agents/templates/agent_mux",
    _ROOT / "src/core/orchestra_agents/templates/opencode",
)
_LEGACY_PACKAGE = _ROOT / "src/core/orchestra_agents/agent_mux_runtime"
_CACHE_DIR_NAME = "__pycache__"
_LEGACY_MODULE_NAME = "core.orchestra_agents.agent_mux_runtime"


def _legacy_python_sources() -> list[Path]:
    if not _LEGACY_PACKAGE.exists():
        return []
    return sorted(
        path for path in _LEGACY_PACKAGE.rglob("*.py") if _CACHE_DIR_NAME not in path.parts
    )


def _legacy_module_spec() -> ModuleSpec | None:
    return util.find_spec(_LEGACY_MODULE_NAME)


def _is_canonical_package_spec(spec: ModuleSpec | None) -> bool:
    return spec is not None and spec.loader is not None


class BackendPackageLayoutTests(unittest.TestCase):
    def test_canonical_backend_packages_exist(self) -> None:
        for package_path in _BACKEND_PATHS:
            with self.subTest(path=str(package_path)):
                self.assertTrue(package_path.exists())

    def test_canonical_backend_templates_exist(self) -> None:
        for template_path in _TEMPLATE_PATHS:
            with self.subTest(path=str(template_path)):
                self.assertTrue(template_path.exists())

    def test_agent_mux_runtime_has_no_python_sources(self) -> None:
        self.assertEqual(_legacy_python_sources(), [])

    def test_agent_mux_runtime_is_not_package(self) -> None:
        self.assertFalse(_is_canonical_package_spec(_legacy_module_spec()))


if __name__ == "__main__":
    unittest.main()
