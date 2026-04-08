from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.manifest import AgentManifest

DockerCommand = list[str]
DockerCommands = list[DockerCommand]
BuildScenarioResult = tuple[dict[str, Any], DockerCommands, Path]

_DRIVER_KEY = "driver"
_IMAGE_KEY = "image"
_DOCKER = "docker"
_RUN_COMMAND = "run"
_DETACHED_FLAG = "-d"
_OPENAI_API_KEY = "OPENAI_API_KEY"
_RUN_PATH = "core.orchestra_agents.docker_driver._run"
_CODING_AGENT_CONTAINER = "orchestra-agent-coding_agent"
_EXISTS_KEY = "exists"
_HEALTHY_KEY = "healthy"
_STATUS_KEY = "status"
_RUNNING_KEY = "running"
_AGENT_IMAGE = "agent-image:latest"
_MUX_RUNTIME_IMAGE = "orchestra-agent-mux-runtime:latest"
_OPENCODE_RUNTIME_IMAGE = "orchestra-opencode-runtime:latest"


def _manifest_payload() -> dict[str, Any]:
    return {
        "slug": "coding_agent",
        "display_name": "Coding Agent",
        _STATUS_KEY: "active",
        "agent": {
            "working_dir": "/workspace",
            "http_endpoint": "http://{container_name}:8787",
            "system_prompt_file": "system_prompt.md",
        },
        "runtime": {
            _DRIVER_KEY: _DOCKER,
            _IMAGE_KEY: _AGENT_IMAGE,
            "command": ["python", "-m", "agent_runtime.main"],
            "mounts": [
                {
                    "type": "bind",
                    "source": ".",
                    "target": "/workspace",
                    "mode": "rw",
                }
            ],
            "env": {"LOG_LEVEL": "INFO"},
            "env_passthrough": [_OPENAI_API_KEY],
        },
        "backend": {"type": "codex_framework"},
    }


def _create_manifest(
    manifests_root: Path,
    *,
    image: str = "agent-image:latest",
    with_system_prompt: bool = False,
) -> AgentManifest:
    agent_dir = manifests_root / "coding_agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = agent_dir / "manifest.yaml"
    manifest_path.write_text("{}", encoding="utf-8")
    if with_system_prompt:
        (agent_dir / "system_prompt.md").write_text("prompt", encoding="utf-8")

    payload = _manifest_payload()
    payload["runtime"][_IMAGE_KEY] = image
    return AgentManifest.from_dict(payload, manifest_path=manifest_path)


class _DockerRunSideEffect:
    def __init__(self) -> None:
        self.commands: DockerCommands = []

    def __call__(self, cmd: DockerCommand, *, timeout: int = 120) -> CompletedProcess[str]:
        if timeout < 0:
            raise AssertionError("timeout must be non-negative")
        self.commands.append(cmd)
        if cmd[:3] == [_DOCKER, "image", "inspect"]:
            return CompletedProcess(cmd, 1, "", "image not found")
        if cmd[:2] == [_DOCKER, "build"]:
            return CompletedProcess(cmd, 0, "built", "")
        if cmd[:2] == [_DOCKER, "stop"]:
            return CompletedProcess(cmd, 0, "stopped\n", "")
        if cmd[:3] == [_DOCKER, "rm", "-f"]:
            return CompletedProcess(cmd, 0, "removed\n", "")
        if cmd[:3] == [_DOCKER, _RUN_COMMAND, _DETACHED_FLAG]:
            return CompletedProcess(cmd, 0, "container-id\n", "")
        raise AssertionError(f"unexpected docker command: {cmd}")


class _DriverScenarios:
    """Reusable test scenarios for DockerDriver tests."""

    @classmethod
    def build_run_command(cls, manifests_root: Path) -> list[str]:
        manifest = _create_manifest(manifests_root, with_system_prompt=True)
        driver = DockerDriver(manifests_root=manifests_root, default_network="agents-net")
        with patch.dict("os.environ", {_OPENAI_API_KEY: "secret"}, clear=False):
            return driver._build_run_command(  # noqa: SLF001
                manifest,
                container_name=_CODING_AGENT_CONTAINER,
            )

    @classmethod
    def start_with_capture(
        cls,
        driver: DockerDriver,
        manifest: AgentManifest,
    ) -> tuple[dict[str, Any], list[str]]:
        status_payload = {_EXISTS_KEY: True, _RUNNING_KEY: True, _HEALTHY_KEY: False}
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=False))
            stack.enter_context(patch.object(driver, "status", return_value=status_payload))
            run_mock = stack.enter_context(
                patch(
                    _RUN_PATH,
                    return_value=CompletedProcess([], 0, "container-id\n", ""),
                )
            )
            cmd_result = driver.start(manifest)
            run_command = list(run_mock.call_args.args[0])
        return cmd_result, run_command

    @classmethod
    def manifest_with_passthrough(cls, root: Path) -> AgentManifest:
        manifest = _create_manifest(root)
        return AgentManifest.from_dict(
            {
                **manifest.to_dict(),
                "runtime": {
                    **manifest.runtime.to_dict(),
                    "env": {_OPENAI_API_KEY: "manifest-secret", "LOG_LEVEL": "INFO"},
                    "env_passthrough": [_OPENAI_API_KEY],
                },
            },
            manifest_path=manifest.manifest_path,
        )

    @classmethod
    def restart_with_capture(
        cls,
        driver: DockerDriver,
        manifest: AgentManifest,
    ) -> _DockerRunSideEffect:
        recorder = _DockerRunSideEffect()
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=True))
            stack.enter_context(
                patch("core.orchestra_agents.docker_driver._run", side_effect=recorder)
            )
            stack.enter_context(
                patch.object(
                    driver,
                    _STATUS_KEY,
                    return_value={
                        _EXISTS_KEY: True,
                        _RUNNING_KEY: True,
                        _HEALTHY_KEY: False,
                    },
                )
            )
            driver.restart(manifest)
        return recorder

    @classmethod
    def start_with_build_capture(
        cls,
        driver: DockerDriver,
        manifest: AgentManifest,
    ) -> tuple[dict[str, Any], _DockerRunSideEffect]:
        recorder = _DockerRunSideEffect()
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=False))
            stack.enter_context(
                patch.object(
                    driver,
                    _STATUS_KEY,
                    return_value={
                        _EXISTS_KEY: True,
                        _RUNNING_KEY: True,
                        _HEALTHY_KEY: False,
                    },
                )
            )
            stack.enter_context(
                patch(_RUN_PATH, side_effect=recorder),
            )
            cmd_result = driver.start(manifest)
        return cmd_result, recorder

    @classmethod
    def run_mux_build(cls, tmpdir: str) -> BuildScenarioResult:
        root = Path(tmpdir)
        agents_root = root / "agents"
        agents_root.mkdir()
        (root / "Dockerfile.agent_mux_runtime").write_text("FROM scratch\n", encoding="utf-8")
        manifest = _create_manifest(agents_root, image=_MUX_RUNTIME_IMAGE)
        driver = DockerDriver(manifests_root=agents_root, build_context_root=root)
        pair = cls.start_with_build_capture(driver, manifest)
        return pair[0], pair[1].commands, root


class DockerDriverTests(unittest.TestCase):
    def test_build_run_cmd_env_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            command = _DriverScenarios.build_run_command(Path(tmpdir))
            rendered = " ".join(command)
            snippets = [
                "--network agents-net",
                "ORCHESTRA_AGENT_MANIFEST=/orchestra/agents/coding_agent/manifest.yaml",
                "ORCHESTRA_AGENT_BACKEND_TYPE=codex_framework",
                "--health-cmd",
                "127.0.0.1:8787/healthz",
                f"{_OPENAI_API_KEY}=secret",
                _AGENT_IMAGE,
            ]
            for snippet in snippets:
                self.assertIn(snippet, rendered)

    def test_status_combines_docker_and_health(self) -> None:
        manifest = AgentManifest.from_dict(_manifest_payload())
        driver = DockerDriver(manifests_root="/tmp")
        state = {
            "Running": True,
            "Status": _RUNNING_KEY,
            "StartedAt": "2025-01-01T00:00:00Z",
            "Error": "",
        }
        with patch(
            _RUN_PATH,
            return_value=CompletedProcess([], 0, json.dumps(state), ""),
        ):
            with patch.object(
                driver,
                "_probe_health",
                return_value={"ok": True, "payload": {_STATUS_KEY: "ok"}},
            ):
                status = driver.status(manifest)

        self.assertTrue(status["exists"])
        self.assertTrue(status[_RUNNING_KEY])
        self.assertTrue(status["healthy"])
        self.assertEqual(status["docker_status"], _RUNNING_KEY)

    def test_start_uses_docker_run_for_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            driver = DockerDriver(manifests_root=root)
            capture = _DriverScenarios.start_with_capture(driver, _create_manifest(root))
            self.assertTrue(capture[0][_EXISTS_KEY])
            self.assertEqual(capture[1][:3], [_DOCKER, _RUN_COMMAND, _DETACHED_FLAG])

    def test_empty_passthrough_keeps_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = _DriverScenarios.manifest_with_passthrough(root)
            driver = DockerDriver(manifests_root=root)
            with patch.dict("os.environ", {_OPENAI_API_KEY: ""}, clear=False):
                rendered = driver._render_env(  # noqa: SLF001
                    manifest,
                    container_name=_CODING_AGENT_CONTAINER,
                )
            self.assertEqual(rendered[_OPENAI_API_KEY], "manifest-secret")

    def test_restart_recreates_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = _create_manifest(root)
            driver = DockerDriver(manifests_root=root)
            recorder = _DriverScenarios.restart_with_capture(driver, manifest)
            _assert_restart_commands(recorder.commands)

    def test_start_builds_missing_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_result, commands, root = _DriverScenarios.run_mux_build(tmpdir)
            self.assertTrue(cmd_result[_EXISTS_KEY])
            _assert_build_cmds(commands, root, "Dockerfile.agent_mux_runtime")

    def test_start_builds_missing_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "Dockerfile.opencode_runtime").write_text("FROM scratch\n", encoding="utf-8")
            cmd_result, recorder = _DriverScenarios.start_with_build_capture(
                DockerDriver(manifests_root=root, build_context_root=root),
                _create_manifest(root, image=_OPENCODE_RUNTIME_IMAGE),
            )
            self.assertTrue(cmd_result[_EXISTS_KEY])
            _assert_build_cmds(recorder.commands, root, "Dockerfile.opencode_runtime")


def _assert_restart_commands(commands: DockerCommands) -> None:
    assert commands[0][:2] == [_DOCKER, "stop"]
    assert commands[0][2] == _CODING_AGENT_CONTAINER
    expected_rm = [_DOCKER, "rm", "-f", _CODING_AGENT_CONTAINER]
    assert commands[1][:4] == expected_rm
    assert commands[-1][:3] == [_DOCKER, _RUN_COMMAND, _DETACHED_FLAG]


def _assert_build_cmds(
    commands: list[list[str]],
    root: Path,
    dockerfile_name: str,
) -> None:
    assert commands[0][:3] == [_DOCKER, "image", "inspect"]
    assert commands[1][:2] == [_DOCKER, "build"]
    assert str(root / dockerfile_name) in commands[1]
    assert commands[2][:3] == [_DOCKER, _RUN_COMMAND, _DETACHED_FLAG]
