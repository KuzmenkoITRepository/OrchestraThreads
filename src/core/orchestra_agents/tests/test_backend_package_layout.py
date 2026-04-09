from __future__ import annotations

import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_PATHS = (
    _ROOT / "src/core/orchestra_agents/backends/sgr",
    _ROOT / "src/core/orchestra_agents/backends/agent_mux",
    _ROOT / "src/core/orchestra_agents/backends/agent_mux/internal",
    _ROOT / "src/core/orchestra_agents/backends/opencode",
)
_LEGACY_PACKAGE = _ROOT / "src/core/orchestra_agents/agent_mux_runtime"


class BackendPackageLayoutTests(unittest.TestCase):
    def test_canonical_backend_packages_exist(self) -> None:
        for package_path in _BACKEND_PATHS:
            with self.subTest(path=str(package_path)):
                self.assertTrue(package_path.exists())

    def test_agent_mux_runtime_package_removed(self) -> None:
        self.assertFalse(_LEGACY_PACKAGE.exists())


if __name__ == "__main__":
    unittest.main()
