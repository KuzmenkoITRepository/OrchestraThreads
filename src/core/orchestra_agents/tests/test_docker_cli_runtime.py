from __future__ import annotations

import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest import mock as umock

from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._docker_run_test_assertions import assert_characterized_run_command
from core.orchestra_agents.tests._docker_runtime_test_scenarios import container_exists_command

_cases = import_module("core.orchestra_agents.tests._docker_cli_runtime_test_cases")
DockerRuntimeLifecycleCases = _cases.DockerRuntimeLifecycleCases
DockerRuntimeStatusCases = _cases.DockerRuntimeStatusCases


class DockerCliRuntimeLifecycleTests(unittest.TestCase):
    def test_start_builds_run_command(self) -> None:
        with tempfile.TemporaryDirectory() as start_dir:
            root = Path(start_dir)
            case = DockerRuntimeLifecycleCases.start(root)
            result = case.runtime.start(case.spec)
            assert case.run_capture is not None

            assert_characterized_run_command(case.run_capture.last_command, manifests_root=root)
            self.assertEqual(result.action, "start")
            self.assertTrue(result.success)
            self.assertIsNone(result.message)

    def test_start_reuses_existing_container(self) -> None:
        with tempfile.TemporaryDirectory() as reuse_dir:
            case = DockerRuntimeLifecycleCases.reuse(Path(reuse_dir))
            result = case.runtime.start(case.spec)

            self.assertEqual(result.message, "container already exists")
            self.assertEqual(
                _runtime_calls(case.shell.calls),
                _expected_runtime_calls(case.spec.container_name),
            )

    def test_stop_removes_existing_container(self) -> None:
        with tempfile.TemporaryDirectory() as stop_dir:
            case = DockerRuntimeLifecycleCases.stop(Path(stop_dir))
            result = case.runtime.stop(case.spec, remove=True)

            self.assertEqual(result.action, "stop")
            self.assertTrue(result.removed)
            self.assertEqual(
                case.shell.calls,
                [
                    container_exists_command(case.spec.container_name),
                    [data.DOCKER, "stop", case.spec.container_name],
                    [data.DOCKER, "rm", "-f", case.spec.container_name],
                ],
            )

    def test_restart_recreates_existing_container(self) -> None:
        with tempfile.TemporaryDirectory() as restart_dir:
            root = Path(restart_dir)
            case = DockerRuntimeLifecycleCases.restart(root)
            result = case.runtime.restart(case.spec)
            assert case.run_capture is not None

            self.assertEqual(result.message, "container recreated")
            assert_characterized_run_command(case.run_capture.last_command, manifests_root=root)


class DockerCliRuntimeStatusTests(unittest.TestCase):
    def test_status_prefers_docker_health(self) -> None:
        with tempfile.TemporaryDirectory() as health_dir:
            case = DockerRuntimeStatusCases.docker_health(Path(health_dir))

            with umock.patch.object(case.runtime, "_probe_health") as probe_health:
                status = case.runtime.status(case.spec)
                probe_health.assert_not_called()

            assert status.health_status is not None
            self.assertFalse(status.healthy)
            self.assertEqual(status.health_status["source"], "docker")

    def test_status_uses_http_probe(self) -> None:
        with tempfile.TemporaryDirectory() as probe_dir:
            case = DockerRuntimeStatusCases.http_probe(Path(probe_dir))
            expected_health = {
                "ok": True,
                "status_code": 200,
                "payload": {data.STATUS_KEY: "ok"},
            }

            with umock.patch.object(case.runtime, "_probe_health", return_value=expected_health):
                status = case.runtime.status(case.spec)

            self.assertTrue(status.healthy)
            self.assertEqual(status.health_status, expected_health)

    def test_status_returns_missing_container_payload(self) -> None:
        with tempfile.TemporaryDirectory() as missing_dir:
            case = DockerRuntimeStatusCases.missing_container(Path(missing_dir))
            status = case.runtime.status(case.spec)

            self.assertFalse(status.exists)
            self.assertEqual(
                status.last_error,
                f"Error: No such container: {case.spec.container_name}",
            )

    def test_builds_missing_known_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as build_dir:
            case = DockerRuntimeStatusCases.build_image(Path(build_dir))
            result = case.runtime.start(case.spec)

            self.assertTrue(result.success)
            self.assertIsNotNone(case.run_capture)


def _runtime_calls(commands: list[list[str]]) -> list[list[str]]:
    result: list[list[str]] = []
    for command in commands:
        if command[:2] != [data.DOCKER, "ps"]:
            result.append(command[:3])
    return result


def _expected_runtime_calls(container_name: str) -> list[list[str]]:
    return [
        [data.DOCKER, "start", container_name],
        [data.DOCKER, "inspect", container_name],
    ]
