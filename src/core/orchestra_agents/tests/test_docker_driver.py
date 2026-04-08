from __future__ import annotations

import json
import os
import tempfile
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.tests import docker_driver_test_assertions as assertions
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests import docker_driver_test_scenarios as scenarios

_CORE_CONTEXT = scenarios.mux_build_context
_COMPOSE_CONTEXT = scenarios.mux_build_context


class DockerDriverCoreTests(unittest.TestCase):
    def test_build_run_cmd_env_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _CORE_CONTEXT(tmpdir)[0]
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
        manifest = AgentManifest.from_dict(data.manifest_payload())
        driver = DockerDriver(manifests_root="/tmp")
        state = {
            "Running": True,
            "Status": data.RUNNING_KEY,
            "StartedAt": "2025-01-01T00:00:00Z",
            "Error": "",
        }
        with patch(
            data.RUN_PATH,
            return_value=CompletedProcess([], 0, json.dumps(state), ""),
        ):
            with patch.object(
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
            root = _CORE_CONTEXT(tmpdir)[0]
            driver = DockerDriver(manifests_root=root)
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
            root = _CORE_CONTEXT(tmpdir)[0]
            manifest = scenarios.DockerScenarios.manifest_with_passthrough(root)
            driver = DockerDriver(manifests_root=root)
            with patch.dict(os.environ, {data.OPENAI_API_KEY: ""}, clear=False):
                rendered = driver._render_env(  # noqa: SLF001
                    manifest,
                    container_name=data.CODING_AGENT_CONTAINER,
                )
            self.assertEqual(rendered[data.OPENAI_API_KEY], "manifest-secret")

    def test_restart_recreates_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _CORE_CONTEXT(tmpdir)[0]
            manifest = data.create_manifest(root)
            driver = DockerDriver(manifests_root=root)
            recorder = scenarios.DockerScenarios.restart_with_capture(driver, manifest)
            assertions.assert_restart_commands(recorder.commands)

    def test_start_builds_missing_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_result, commands, root = scenarios.DockerScenarios.run_mux_build(tmpdir)
            self.assertTrue(cmd_result[data.EXISTS_KEY])
            assertions.assert_build_cmds(commands, root, "Dockerfile.agent_mux_runtime")

    def test_start_builds_missing_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _CORE_CONTEXT(tmpdir)[0]
            dockerfile = root / "Dockerfile.opencode_runtime"
            dockerfile.write_text("FROM scratch\n", encoding="utf-8")
            cmd_result, recorder = scenarios.DockerScenarios.start_with_build_capture(
                DockerDriver(manifests_root=root, build_context_root=root),
                data.create_manifest(
                    root,
                    image=data.OPENCODE_RUNTIME_IMAGE,
                ),
            )
            self.assertTrue(cmd_result[data.EXISTS_KEY])
            assertions.assert_build_cmds(
                recorder.commands,
                root,
                "Dockerfile.opencode_runtime",
            )


class DockerDriverComposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._compose_env_patch = patch.dict(
            os.environ,
            {data.COMPOSE_ENV_KEY: ""},
            clear=False,
        )
        self._compose_env_patch.start()

    def tearDown(self) -> None:
        self._compose_env_patch.stop()

    def test_start_uses_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _COMPOSE_CONTEXT(tmpdir)[0]
            assertions.assert_compose_start(
                scenarios.ComposeScenarios.start_with_capture(root),
            )

    def test_stop_uses_compose_rm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _COMPOSE_CONTEXT(tmpdir)[0]
            assertions.assert_compose_stop(
                scenarios.ComposeScenarios.stop_with_capture(root, remove=True),
            )

    def test_stop_fails_without_compose_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _COMPOSE_CONTEXT(tmpdir)[0]
            driver, recorder = scenarios.ComposeScenarios.stop_missing_file_with_capture(root)
            with patch(data.RUN_PATH, side_effect=recorder):
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
