from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class ImportRecord:
    source_module: str
    target_module: str
    file_path: Path
    line_number: int


@dataclass(frozen=True)
class Config:
    root: Path
    src_root: Path
    backends_root: Path
    templates_root: Path
    legacy_path: Path
    backend_prefix: str
    template_prefix: str
    legacy_prefix: str
    diff_target: str
    tolerated_edges: frozenset[tuple[str, str]]
    template_specs: tuple[tuple[Path, str, str], ...]
    owned_diff_patterns: tuple[str, ...]


@dataclass(frozen=True)
class ImportIndex:
    config: Config
    backend_depth: int = 3

    def python_files(self, root: Path) -> tuple[Path, ...]:
        return tuple(sorted(root.glob("**/*.py")))

    def parse_imports(self, file_path: Path) -> tuple[ImportRecord, ...]:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        source_module = self._module_path(file_path)
        records: list[ImportRecord] = []
        for node in ast.walk(tree):
            records.extend(self._node_records(node, source_module, file_path))
        return tuple(records)

    def backend_name(self, module_name: str) -> str | None:
        if not module_name.startswith(self.config.backend_prefix):
            return None
        return module_name.removeprefix(self.config.backend_prefix).split(".", 1)[0]

    def location(self, record: ImportRecord) -> str:
        return f"{record.file_path.relative_to(self.config.root)}:{record.line_number}"

    def _module_path(self, file_path: Path) -> str:
        parts = list(file_path.relative_to(self.config.src_root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def _node_records(
        self,
        node: ast.AST,
        source_module: str,
        file_path: Path,
    ) -> tuple[ImportRecord, ...]:
        if isinstance(node, ast.Import):
            return tuple(
                ImportRecord(source_module, alias.name, file_path, node.lineno)
                for alias in node.names
            )
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            return ()
        return tuple(
            ImportRecord(
                source_module,
                self._import_target(node.module, alias.name),
                file_path,
                node.lineno,
            )
            for alias in node.names
        )

    def _import_target(self, module_name: str, imported_name: str) -> str:
        is_backend_root = (
            module_name.startswith(self.config.backend_prefix)
            and module_name.count(".") == self.backend_depth
        )
        if is_backend_root and imported_name == imported_name.lower():
            return f"{module_name}.{imported_name}"
        return module_name


@dataclass(frozen=True)
class BoundaryChecks:
    imports: ImportIndex

    @property
    def config(self) -> Config:
        return self.imports.config

    def cross_backend(self) -> tuple[tuple[str, str], ...]:
        edge_locations = self._edge_locations()
        actual_edges = frozenset(edge_locations)
        missing = tuple(
            (f"missing:{edge}", f"Missing tolerated cross-backend edge: {edge}")
            for edge in sorted(self.config.tolerated_edges - actual_edges)
        )
        unexpected = tuple(
            (
                f"unexpected:{edge}",
                f"Unexpected cross-backend edge {edge} at {', '.join(edge_locations[edge])}",
            )
            for edge in sorted(actual_edges - self.config.tolerated_edges)
        )
        return missing + unexpected

    def template_boundaries(self) -> tuple[tuple[str, str], ...]:
        violations: list[tuple[str, str]] = []
        for runtime_root, backend_prefix, template_prefix in self.config.template_specs:
            violations.extend(
                self._template_violations(runtime_root, backend_prefix, template_prefix)
            )
        return tuple(violations)

    def _edge_locations(self) -> dict[tuple[str, str], list[str]]:
        edge_locations: dict[tuple[str, str], list[str]] = {}
        for file_path in self.imports.python_files(self.config.backends_root):
            for record in self.imports.parse_imports(file_path):
                edge = self._edge_for_record(record)
                if edge is None:
                    continue
                edge_locations.setdefault(edge, []).append(self.imports.location(record))
        return edge_locations

    def _edge_for_record(self, record: ImportRecord) -> tuple[str, str] | None:
        source_backend = self.imports.backend_name(record.source_module)
        target_backend = self.imports.backend_name(record.target_module)
        if source_backend is None or target_backend is None:
            return None
        if source_backend == target_backend:
            return None
        return (record.source_module, record.target_module)

    def _template_violations(
        self,
        runtime_root: Path,
        backend_prefix: str,
        template_prefix: str,
    ) -> tuple[tuple[str, str], ...]:
        violations: list[tuple[str, str]] = []
        for file_path in self.imports.python_files(runtime_root):
            for record in self.imports.parse_imports(file_path):
                if self._template_allowed(record, backend_prefix, template_prefix):
                    continue
                violations.append(
                    (
                        f"{file_path.relative_to(self.config.root)}:{record.target_module}",
                        f"{record.target_module} from {self.imports.location(record)} violates template wrapper boundary",
                    )
                )
        return tuple(violations)

    def _template_allowed(
        self,
        record: ImportRecord,
        backend_prefix: str,
        template_prefix: str,
    ) -> bool:
        target_module = record.target_module
        if target_module.startswith(self.config.backend_prefix):
            return target_module.startswith(backend_prefix)
        if target_module.startswith(self.config.template_prefix):
            return target_module.startswith(template_prefix)
        return True


@dataclass(frozen=True)
class OwnershipChecks:
    imports: ImportIndex

    @property
    def config(self) -> Config:
        return self.imports.config

    def legacy_boundary(self) -> tuple[tuple[str, str], ...]:
        violations = list(self._legacy_source_violations())
        violations.extend(self._legacy_import_violations(self.config.backends_root))
        for runtime_root, _, _ in self.config.template_specs:
            violations.extend(self._legacy_import_violations(runtime_root))
        return tuple(violations)

    def diff_allowlist(self) -> tuple[tuple[str, str], ...]:
        result = subprocess.run(
            ("git", "diff", "--name-only", self.config.diff_target),
            capture_output=True,
            check=False,
            cwd=self.config.root,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            return (("git-diff", f"git diff failed: {detail}"),)
        return tuple(
            (
                path_name,
                f"Out-of-scope branch diff path against {self.config.diff_target}: {path_name}",
            )
            for path_name in self._changed_paths(result.stdout)
            if not self._is_owned_diff_path(path_name)
        )

    def _changed_paths(self, stdout: str) -> tuple[str, ...]:
        paths: list[str] = []
        for line in stdout.splitlines():
            path_name = line.strip()
            if path_name:
                paths.append(path_name)
        return tuple(paths)

    def _is_owned_diff_path(self, path_name: str) -> bool:
        return any(fnmatch(path_name, pattern) for pattern in self.config.owned_diff_patterns)

    def _legacy_source_violations(self) -> tuple[tuple[str, str], ...]:
        sources = tuple(
            sorted(
                str(path.relative_to(self.config.root))
                for path in self.config.legacy_path.glob("**/*.py")
            )
        )
        if not sources:
            return ()
        return (
            (
                "legacy-source",
                f"Legacy agent_mux_runtime regained Python source files: {sources}",
            ),
        )

    def _legacy_import_violations(self, root: Path) -> tuple[tuple[str, str], ...]:
        violations: list[tuple[str, str]] = []
        for file_path in self.imports.python_files(root):
            for record in self.imports.parse_imports(file_path):
                if not record.target_module.startswith(self.config.legacy_prefix):
                    continue
                violations.append(
                    (
                        f"{file_path.relative_to(self.config.root)}:{record.target_module}",
                        "Owned backend code must not import legacy agent_mux_runtime: "
                        f"{record.target_module} from {self.imports.location(record)}",
                    )
                )
        return tuple(violations)


def build_config() -> Config:
    root = Path(__file__).resolve().parents[4]
    src_root = root / "src"
    templates_root = src_root / "core/orchestra_agents/templates"
    return Config(
        root=root,
        src_root=src_root,
        backends_root=src_root / "core/orchestra_agents/backends",
        templates_root=templates_root,
        legacy_path=src_root / "core/orchestra_agents/agent_mux_runtime",
        backend_prefix="core.orchestra_agents.backends.",
        template_prefix="core.orchestra_agents.templates.",
        legacy_prefix="core.orchestra_agents.agent_mux_runtime",
        diff_target="structure-refactoring...HEAD",
        tolerated_edges=frozenset(
            (
                (
                    "core.orchestra_agents.backends.agent_mux.backend",
                    "core.orchestra_agents.backends.opencode.backend_registration",
                ),
                (
                    "core.orchestra_agents.backends.sgr.backend",
                    "core.orchestra_agents.backends.opencode.backend_registration",
                ),
                (
                    "core.orchestra_agents.backends.sgr.config_builder",
                    "core.orchestra_agents.backends.agent_mux.normalization",
                ),
                (
                    "core.orchestra_agents.backends.sgr.llm_client",
                    "core.orchestra_agents.backends.agent_mux.normalization",
                ),
                (
                    "core.orchestra_agents.backends.sgr.support.event_metadata",
                    "core.orchestra_agents.backends.agent_mux.normalization",
                ),
                (
                    "core.orchestra_agents.backends.sgr.support.outcomes",
                    "core.orchestra_agents.backends.agent_mux.normalization",
                ),
                (
                    "core.orchestra_agents.backends.sgr.tool_exec",
                    "core.orchestra_agents.backends.agent_mux.normalization",
                ),
            )
        ),
        template_specs=(
            (
                templates_root / "agent" / "agent_runtime",
                "core.orchestra_agents.backends.example",
                "core.orchestra_agents.templates.agent.agent_runtime",
            ),
            (
                templates_root / "agent_mux" / "agent_runtime",
                "core.orchestra_agents.backends.agent_mux",
                "core.orchestra_agents.templates.agent_mux.agent_runtime",
            ),
            (
                templates_root / "opencode" / "agent_runtime",
                "core.orchestra_agents.backends.opencode",
                "core.orchestra_agents.templates.opencode.agent_runtime",
            ),
        ),
        owned_diff_patterns=(
            "src/core/orchestra_agents/backends/**",
            "src/core/orchestra_agents/templates/**",
            "src/core/orchestra_agents/tests/test_backend_*.py",
            "src/core/orchestra_agents/tests/test_agent_mux_*.py",
            "src/core/orchestra_agents/tests/test_opencode_*.py",
            "src/core/orchestra_agents/tests/test_sgr_*.py",
            "src/core/orchestra_agents/tests/test_agent_layout.py",
            "src/core/orchestra_agents/tests/test_template_wrapper_boundaries.py",
            "src/core/orchestra_agents/tests/test_backend_scope_guards.py",
            ".sisyphus/evidence/**",
        ),
    )


def run_diff(config: Config) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ("git", "diff", "--name-only", config.diff_target),
            capture_output=True,
            check=False,
            cwd=config.root,
            text=True,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=("git", "diff", "--name-only", config.diff_target),
            returncode=0,
            stdout="",
            stderr="",
        )
