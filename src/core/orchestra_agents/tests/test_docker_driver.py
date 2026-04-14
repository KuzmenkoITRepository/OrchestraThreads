from __future__ import annotations

import json
import tempfile
from importlib import import_module
from pathlib import Path
from subprocess import CompletedProcess
from unittest import TestCase
from unittest import mock as umock

from core.orchestra_agents import (
    manifest as manifest_module,
)
from core.orchestra_agents.tests import docker_driver_test_assertions as assertions
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests import docker_driver_test_scenarios as scenarios

docker_driver_module = import_module("core.orchestra_agents.docker_driver.driver")

_CORE_CONTEXT = scenarios.mux_build_context


def _legacy_manifest(root: Path) -> manifest_module.AgentManifest:
    return data.create_manifest(root, image=data.AGENT_IMAGE)


def _legacy_rendered_env(
    root: Path,
) -> tuple[manifest_module.AgentManifest, dict[str, str]]:
    legacy = _legacy_manifest(root)
    driver = docker_driver_module.DockerDriver(manifests_root=root)
    rendered = driver._render_env(  # noqa: SLF001
        legacy,
        docker_driver_module.resolve_backend_runtime(legacy),
        container_name=data.CODING_AGENT_CONTAINER,
    )
    return legacy, rendered


class _DockerDriverRootMixin:
    @staticmethod
    def root(tmpdir: str) -> Path:
        return _CORE_CONTEXT(tmpdir)[0]


class DockerDriverCoreTests(_DockerDriverRootMixin, TestCase):
    def test_build_run_cmd_env_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            command = scenarios.DockerScenarios.build_run_command(root)
            rendered = " ".join(command)
            for snippet in (
                "--network agents-net",
                "ORCHESTRA_AGENT_MANIFEST=/orchestra/agents/coding_agent/manifest.yaml",
                "ORCHESTRA_AGENT_BACKEND_TYPE=codex_framework",
                "--health-cmd",
                "127.0.0.1:8787/healthz",
                f"{data.OPENAI_API_KEY}=secret",
                data.AGENT_IMAGE,
            ):
                self.assertIn(snippet, rendered)

    def test_status_combines_docker_and_health(self) -> None:
        manifest = data.create_manifest(Path("/tmp"), image=data.AGENT_IMAGE)
        driver = docker_driver_module.DockerDriver(manifests_root="/tmp")
        state = {
            "Running": True,
            "Status": data.RUNNING_KEY,
            "StartedAt": "2025-01-01T00:00:00Z",
            "Error": "",
        }
        with umock.patch(
            data.RUN_PATH,
            return_value=CompletedProcess([], 0, json.dumps(state), ""),
        ):
            with umock.patch.object(
                driver,
                "_probe_health",
                return_value={"ok": True, "payload": {data.STATUS_KEY: "ok"}},
            ):
                status = driver.status(manifest)

        self.assertTrue(status[data.EXISTS_KEY])
        self.assertTrue(status[data.RUNNING_KEY])
        self.assertTrue(status["healthy"])
        self.assertEqual(status["docker_status"], data.RUNNING_KEY)

    def test_start_uses_docker_run_for_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            driver = docker_driver_module.DockerDriver(manifests_root=root)
            cmd_result, command = scenarios.DockerScenarios.start_with_capture(
                driver,
                data.create_manifest(root),
            )
            self.assertTrue(cmd_result[data.EXISTS_KEY])
            self.assertEqual(
                command[:3],
                [
                    data.DOCKER,
                    data.RUN_COMMAND,
                    data.DETACHED_FLAG,
                ],
            )

    def test_empty_passthrough_keeps_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            manifest = scenarios.DockerScenarios.manifest_with_passthrough(root)
            driver = docker_driver_module.DockerDriver(manifests_root=root)
            with umock.patch.dict("os.environ", {data.OPENAI_API_KEY: ""}, clear=False):
                rendered = driver._render_env(  # noqa: SLF001
                    manifest,
                    docker_driver_module.resolve_backend_runtime(manifest),
                    container_name=data.CODING_AGENT_CONTAINER,
                )
            self.assertEqual(rendered[data.OPENAI_API_KEY], "manifest-secret")

    def test_restart_recreates_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            manifest = data.create_manifest(root)
            driver = docker_driver_module.DockerDriver(manifests_root=root)
            recorder = scenarios.DockerScenarios.restart_with_capture(driver, manifest)
            assertions.assert_restart_commands(recorder.commands)

    def test_start_builds_missing_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_result, commands, root = scenarios.DockerScenarios.run_mux_build(tmpdir)
            self.assertTrue(cmd_result[data.EXISTS_KEY])
            assertions.assert_build_cmds(commands, root, "docker/backends/agent_mux/Dockerfile")

    def test_start_builds_missing_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            dockerfile = root / "docker" / "backends" / "opencode" / "Dockerfile"
            dockerfile.parent.mkdir(parents=True, exist_ok=True)
            dockerfile.write_text("FROM scratch\n", encoding="utf-8")
            cmd_result, recorder = scenarios.DockerScenarios.start_with_build_capture(
                docker_driver_module.DockerDriver(manifests_root=root, build_context_root=root),
                data.create_manifest(
                    root,
                    image=data.OPENCODE_RUNTIME_IMAGE,
                ),
            )
            self.assertTrue(cmd_result[data.EXISTS_KEY])
            assertions.assert_build_cmds(
                recorder.commands,
                root,
                "docker/backends/opencode/Dockerfile",
            )


class DockerDriverRuntimeResolutionTests(_DockerDriverRootMixin, TestCase):
    def test_agent_mux_runtime_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            command = scenarios.DockerScenarios.build_unified_run_command(
                root,
                backend_type="agent_mux",
            )
            assertions.assert_runtime_resolution(
                command,
                image=data.MUX_RUNTIME_IMAGE,
                module="core.orchestra_agents.backends.agent_mux.main",
                pythonpath="/workspace/src",
            )

    def test_sgr_runtime_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            command = scenarios.DockerScenarios.build_unified_run_command(
                root,
                backend_type="sgr_minimax",
            )
            assertions.assert_runtime_resolution(
                command,
                image=data.SGR_RUNTIME_IMAGE,
                module="core.orchestra_agents.backends.sgr.main",
                pythonpath="/workspace/src:/workspace",
            )

    def test_opencode_runtime_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            command = scenarios.DockerScenarios.build_unified_run_command(
                root,
                backend_type="opencode_omo",
            )
            assertions.assert_runtime_resolution(
                command,
                image=data.OPENCODE_RUNTIME_IMAGE,
                module="core.orchestra_agents.backends.opencode.main",
                pythonpath="/workspace/src",
            )

    def test_legacy_runtime_overrides_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            legacy, rendered = _legacy_rendered_env(root)

            self.assertEqual(legacy.runtime.image, data.AGENT_IMAGE)
            self.assertEqual(
                docker_driver_module.resolve_backend_runtime(legacy).image, data.AGENT_IMAGE
            )
            self.assertEqual(rendered["LOG_LEVEL"], "INFO")


class DockerDriverComposeTests(_DockerDriverRootMixin, TestCase):
    def setUp(self) -> None:
        self._compose_env_patch = umock.patch.dict(
            "os.environ",
            {data.COMPOSE_ENV_KEY: ""},
            clear=False,
        )
        self._compose_env_patch.start()

    def tearDown(self) -> None:
        self._compose_env_patch.stop()

    def test_start_uses_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            assertions.assert_compose_start(
                scenarios.ComposeScenarios.start_with_capture(root),
            )

    def test_stop_uses_compose_rm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            assertions.assert_compose_stop(
                scenarios.ComposeScenarios.stop_with_capture(root, remove=True),
            )

    def test_stop_fails_without_compose_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.root(tmpdir)
            driver, recorder = scenarios.ComposeScenarios.stop_missing_file_with_capture(root)
            with umock.patch(data.RUN_PATH, side_effect=recorder):
                with self.assertRaisesRegex(RuntimeError, "compose metadata missing"):
                    driver.stop("coding_agent", remove=True)
            self.assertEqual(
                recorder.commands,
                [
                    [
                        data.DOCKER,
                        "ps",
                        "-a",
                        "--filter",
                        f"name=^{data.CODING_AGENT_CONTAINER}$",
                        "--format",
                        "{{.Names}}",
                    ],
                ],
            )

    def test_resolves_relative_bind_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            host_root = Path(tmpdir) / "host-workspace"
            (host_root / "agents" / "secretary").mkdir(parents=True)
            manifest = manifest_module.AgentManifest.from_dict(
                {
                    "slug": "secretary",
                    "display_name": "Secretary",
                    "status": "active",
                    "agent": {
                        "working_dir": "/workspace/agents/secretary",
                        "http_endpoint": "http://{container_name}:8787",
                    },
                    "runtime": {
                        "driver": "docker",
                        "image": data.SGR_RUNTIME_IMAGE,
                        "mounts": [
                            {
                                "type": "bind",
                                "source": "../../",
                                "target": "/workspace",
                                "mode": "rw",
                            }
                        ],
                    },
                    "backend": {
                        "type": "sgr_minimax",
                        "config": {"route_policy": "codex_only", "model": "cx/gpt-5.4-mini"},
                    },
                },
                manifest_path=Path("/container/agents/secretary/manifest.yaml"),
            )
            driver = docker_driver_module.DockerDriver(
                manifests_root="/container/agents",
                host_manifests_root=host_root / "agents",
                compose_project_name=data.COMPOSE_PROJECT,
                compose_runtime_dir=host_root / "compose-runtime",
            )

            mount_spec = driver._render_mount_spec(  # noqa: SLF001
                manifest,
                manifest.runtime.mounts[0],
                container_name="orchestra-agent-secretary",
            )

            self.assertEqual(f"{host_root}:/workspace:rw", mount_spec)
