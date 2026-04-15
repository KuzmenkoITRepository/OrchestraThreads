from __future__ import annotations

import tempfile
from importlib import import_module
from pathlib import Path
from unittest import TestCase
from unittest import mock as umock

from core.orchestra_agents.launch._runtime_shell import ShellResult
from core.orchestra_agents.launch.compose_runtime import ComposeRuntime
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._compose_runtime_test_assertions import (
    assert_characterized_compose_start,
    assert_compose_stop,
)
from core.orchestra_agents.tests._runtime_shell_fakes import QueueShellRunner

_case_mod = import_module("core.orchestra_agents.tests._compose_runtime_test_cases")
ComposeCaseFactory = _case_mod.ComposeCaseFactory

_scenario_mod = import_module("core.orchestra_agents.tests._compose_runtime_test_scenarios")
http_error = _scenario_mod.http_error
missing_container_spec = _scenario_mod.missing_container_spec
running_state_result = _scenario_mod.running_state_result
status_spec = _scenario_mod.status_spec
unhealthy_state_result = _scenario_mod.unhealthy_state_result

_support_mod = import_module("core.orchestra_agents.tests._compose_runtime_test_support")
build_dockerfile_arg = _support_mod.build_dockerfile_arg
compose_capture = _support_mod.compose_capture
compose_stop_capture = _support_mod.compose_stop_capture


def _probe_health(runtime: ComposeRuntime, endpoint: str) -> dict[str, object]:
    return runtime._probe_health(endpoint)


class ComposeRuntimeStartTests(TestCase):
    def test_start_writes_characterized_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case = ComposeCaseFactory.characterized_start(Path(tmpdir))
            result = case.runtime.start(case.spec)

            self.assertTrue(result.success)
            assert_characterized_compose_start(compose_capture(case), manifests_root=case.root)

    def test_start_replaces_legacy_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case = ComposeCaseFactory.legacy_replace(Path(tmpdir))
            result = case.runtime.start(case.spec)

            self.assertTrue(result.success)
            self.assertEqual(
                case.shell.calls[3][0],
                ["docker", "rm", "-f", data.CODING_AGENT_CONTAINER],
            )

    def test_start_builds_missing_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case, dockerfile = ComposeCaseFactory.missing_image(Path(tmpdir))
            result = case.runtime.start(case.spec)

            self.assertTrue(result.success)
            self.assertEqual(build_dockerfile_arg(case.shell), str(dockerfile.resolve()))


class ComposeRuntimeLifecycleTests(TestCase):
    def test_restart_uses_force_recreate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case = ComposeCaseFactory.restart(Path(tmpdir))
            result = case.runtime.restart(case.spec)

            self.assertTrue(result.success)
            self.assertIn("--force-recreate", case.shell.calls[2][0])

    def test_stop_remove_cleans_compose_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case = ComposeCaseFactory.stop(Path(tmpdir))
            result = case.runtime.stop(case.spec, remove=True)

            self.assertTrue(result.removed)
            assert_compose_stop(compose_stop_capture(case, result.removed))

    def test_stop_rejects_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case = ComposeCaseFactory.missing_metadata(Path(tmpdir))

            with self.assertRaisesRegex(RuntimeError, "compose metadata missing"):
                case.runtime.stop(case.spec, remove=True)


class ComposeRuntimeStatusTests(TestCase):
    def test_status_prefers_docker_health(self) -> None:
        shell = QueueShellRunner()
        shell.push(unhealthy_state_result())
        runtime = ComposeRuntime(compose_project_name=data.COMPOSE_PROJECT, shell_runner=shell)

        with umock.patch.object(runtime, "_probe_health") as probe_health:
            status = runtime.status(status_spec())
            probe_health.assert_not_called()

        assert status.health_status is not None
        self.assertFalse(status.healthy)
        self.assertEqual(status.health_status["source"], "docker")

    def test_status_uses_http_probe(self) -> None:
        shell = QueueShellRunner()
        shell.push(running_state_result())
        runtime = ComposeRuntime(compose_project_name=data.COMPOSE_PROJECT, shell_runner=shell)

        with umock.patch.object(runtime, "_probe_health", return_value={"ok": True}):
            status = runtime.status(status_spec())

        self.assertTrue(status.healthy)
        self.assertEqual(status.health_status, {"ok": True})

    def test_status_returns_missing_payload(self) -> None:
        shell = QueueShellRunner()
        shell.push(ShellResult(1, stderr="No such container\n"))
        runtime = ComposeRuntime(compose_project_name=data.COMPOSE_PROJECT, shell_runner=shell)

        status = runtime.status(missing_container_spec())

        self.assertFalse(status.exists)
        self.assertEqual(status.last_error, "No such container")

    def test_read_health_payload_wraps_http_errors(self) -> None:
        runtime = ComposeRuntime(compose_project_name=data.COMPOSE_PROJECT)

        with umock.patch.object(runtime, "_read_health_payload", side_effect=http_error()):
            payload = _probe_health(runtime, "http://127.0.0.1:8787")

        self.assertEqual(payload, {"ok": False, "status_code": 500, "error": "boom"})
