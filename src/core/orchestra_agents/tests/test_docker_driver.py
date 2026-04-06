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


def _manifest_payload() -> dict[str, Any]:
    return {
        "slug": "coding_agent",
        "display_name": "Coding Agent",
        "status": "active",
        "agent": {
            "working_dir": "/workspace",
            "http_endpoint": "http://{container_name}:8787",
            "system_prompt_file": "system_prompt.md",
        },
        "runtime": {
            "driver": "docker",
            "image": "agent-image:latest",
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
            "env_passthrough": ["OPENAI_API_KEY"],
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
    payload["runtime"]["image"] = image
    return AgentManifest.from_dict(payload, manifest_path=manifest_path)


def _build_run_command(manifests_root: Path) -> list[str]:
    manifest = _create_manifest(manifests_root, with_system_prompt=True)
    driver = DockerDriver(manifests_root=manifests_root, default_network="agents-net")
    with patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=False):
        return driver._build_run_command(  # noqa: SLF001
            manifest,
            container_name="orchestra-agent-coding_agent",
        )


def _start_with_run_capture(
    driver: DockerDriver,
    manifest: AgentManifest,
) -> tuple[dict[str, Any], list[str]]:
    status_payload = {"exists": True, "running": True, "healthy": False}
    with ExitStack() as stack:
        stack.enter_context(patch.object(driver, "_container_exists", return_value=False))
        stack.enter_context(patch.object(driver, "status", return_value=status_payload))
        run_mock = stack.enter_context(
            patch(
                "core.orchestra_agents.docker_driver._run",
                return_value=CompletedProcess([], 0, "container-id\n", ""),
            )
        )
        result = driver.start(manifest)
        run_command = list(run_mock.call_args.args[0])
    return result, run_command


class _DockerRunSideEffect:
    def __init__(self) -> None:
        self.commands: DockerCommands = []

    def __call__(self, cmd: DockerCommand, *, timeout: int = 120) -> CompletedProcess[str]:
        if timeout < 0:
            raise AssertionError("timeout must be non-negative")
        self.commands.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return CompletedProcess(cmd, 1, "", "image not found")
        if cmd[:2] == ["docker", "build"]:
            return CompletedProcess(cmd, 0, "built", "")
        if cmd[:3] == ["docker", "run", "-d"]:
            return CompletedProcess(cmd, 0, "container-id\n", "")
        raise AssertionError(f"unexpected docker command: {cmd}")


def _assert_build_commands(commands: list[list[str]], root: Path) -> None:
    inspect_cmd = commands[0]
    build_cmd = commands[1]
    run_cmd = commands[2]
    assert inspect_cmd[:3] == ["docker", "image", "inspect"]
    assert build_cmd[:2] == ["docker", "build"]
    assert str(root / "Dockerfile.agent_mux_runtime") in build_cmd
    assert run_cmd[:3] == ["docker", "run", "-d"]


class DockerDriverTests(unittest.TestCase):
    def test_build_run_cmd_env_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            command = _build_run_command(Path(tmpdir))
            rendered = " ".join(command)
            snippets = [
                "--network agents-net",
                "ORCHESTRA_AGENT_MANIFEST=/orchestra/agents/coding_agent/manifest.yaml",
                "ORCHESTRA_AGENT_BACKEND_TYPE=codex_framework",
                "--health-cmd",
                "127.0.0.1:8787/healthz",
                "OPENAI_API_KEY=secret",
                "agent-image:latest",
            ]
            for snippet in snippets:
                self.assertIn(snippet, rendered)

    def test_status_combines_docker_and_health(self) -> None:
        manifest = AgentManifest.from_dict(_manifest_payload())
        driver = DockerDriver(manifests_root="/tmp")
        state = {
            "Running": True,
            "Status": "running",
            "StartedAt": "2025-01-01T00:00:00Z",
            "Error": "",
        }
        with patch(
            "core.orchestra_agents.docker_driver._run",
            return_value=CompletedProcess([], 0, json.dumps(state), ""),
        ):
            with patch.object(
                driver, "_probe_health", return_value={"ok": True, "payload": {"status": "ok"}}
            ):
                status = driver.status(manifest)

        self.assertTrue(status["exists"])
        self.assertTrue(status["running"])
        self.assertTrue(status["healthy"])
        self.assertEqual(status["docker_status"], "running")

    def test_start_uses_docker_run_for_new_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = _create_manifest(Path(tmpdir))
            driver = DockerDriver(manifests_root=Path(tmpdir))
            result, run_command = _start_with_run_capture(driver, manifest)
            self.assertTrue(result["exists"])
            self.assertEqual(run_command[:3], ["docker", "run", "-d"])

    def test_start_builds_missing_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result, commands, root = self._run_build_scenario(tmpdir)
            self.assertTrue(result["exists"])
            _assert_build_commands(commands, root)

    def _build_driver_case(self, root: Path) -> tuple[DockerDriver, AgentManifest]:
        agents_root = root / "agents"
        agents_root.mkdir()
        (root / "Dockerfile.agent_mux_runtime").write_text("FROM scratch\n", encoding="utf-8")
        manifest = _create_manifest(agents_root, image="orchestra-agent-mux-runtime:latest")
        driver = DockerDriver(manifests_root=agents_root, build_context_root=root)
        return driver, manifest

    def _run_build_scenario(self, tmpdir: str) -> BuildScenarioResult:
        root = Path(tmpdir)
        driver, manifest = self._build_driver_case(root)
        recorder = _DockerRunSideEffect()

        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=False))
            stack.enter_context(
                patch.object(
                    driver,
                    "status",
                    return_value={"exists": True, "running": True, "healthy": False},
                )
            )
            stack.enter_context(
                patch("core.orchestra_agents.docker_driver._run", side_effect=recorder)
            )
            return driver.start(manifest), recorder.commands, root
