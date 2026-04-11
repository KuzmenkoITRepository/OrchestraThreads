from __future__ import annotations

import importlib
import sys
import unittest
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.append(str(_TESTS_DIR))

_SUPPORT_MODULE = importlib.import_module("_backend_scope_guard_support")
BoundaryChecks = _SUPPORT_MODULE.BoundaryChecks
ImportIndex = _SUPPORT_MODULE.ImportIndex
OwnershipChecks = _SUPPORT_MODULE.OwnershipChecks
build_config = _SUPPORT_MODULE.build_config
run_diff = _SUPPORT_MODULE.run_diff


class _BoundaryCheckProtocol(Protocol):
    def cross_backend(self) -> tuple[tuple[str, str], ...]: ...

    def template_boundaries(self) -> tuple[tuple[str, str], ...]: ...


class _OwnershipCheckProtocol(Protocol):
    def legacy_boundary(self) -> tuple[tuple[str, str], ...]: ...


class BackendScopeGuardTests(unittest.TestCase):
    def test_cross_backend_baseline(self) -> None:
        boundary_checks, _ = self._checks()
        for label, detail in boundary_checks.cross_backend():
            with self.subTest(violation=label):
                self.fail(detail)

    def test_template_wrapper_boundaries(self) -> None:
        boundary_checks, _ = self._checks()
        for label, detail in boundary_checks.template_boundaries():
            with self.subTest(violation=label):
                self.fail(detail)

    def test_legacy_boundary(self) -> None:
        _, ownership_checks = self._checks()
        for label, detail in ownership_checks.legacy_boundary():
            with self.subTest(violation=label):
                self.fail(detail)

    def test_branch_diff_allowlist(self) -> None:
        config = build_config()
        result = run_diff(config)
        if result.returncode != 0:
            self.fail(f"git diff failed: {result.stderr.strip() or result.stdout.strip()}")
        for path_name in self._changed_paths(result.stdout):
            is_owned = any(fnmatch(path_name, pattern) for pattern in config.owned_diff_patterns)
            with self.subTest(violation=path_name):
                self.assertTrue(
                    is_owned,
                    f"Out-of-scope branch diff path against {config.diff_target}: {path_name}",
                )

    @staticmethod
    def _checks() -> tuple[_BoundaryCheckProtocol, _OwnershipCheckProtocol]:
        config = build_config()
        imports = ImportIndex(config=config)
        return BoundaryChecks(imports=imports), OwnershipChecks(imports=imports)

    @staticmethod
    def _changed_paths(stdout: str) -> tuple[str, ...]:
        paths: list[str] = []
        for line in stdout.splitlines():
            path_name = line.strip()
            if path_name:
                paths.append(path_name)
        return tuple(paths)


if __name__ == "__main__":
    unittest.main()
