from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.tests import docker_driver_test_data as data


class DockerRunRecorder:
    def __init__(self) -> None:
        self.commands: data.DockerCommands = []

    def __call__(
        self,
        cmd: data.DockerCommand,
        *,
        timeout: int = 120,
    ) -> CompletedProcess[str]:
        if timeout < 0:
            raise AssertionError("timeout must be non-negative")
        self.commands.append(cmd)
        prefix_two = cmd[:2]
        prefix_three = cmd[:3]
        if prefix_three == [data.DOCKER, "image", "inspect"]:
            return CompletedProcess(cmd, 1, "", "image not found")
        if prefix_two == [data.DOCKER, "build"]:
            return CompletedProcess(cmd, 0, "built", "")
        if prefix_two == [data.DOCKER, "stop"]:
            return CompletedProcess(cmd, 0, "stopped\n", "")
        if prefix_three == [data.DOCKER, "rm", "-f"]:
            return CompletedProcess(cmd, 0, "removed\n", "")
        if prefix_three == [data.DOCKER, data.RUN_COMMAND, data.DETACHED_FLAG]:
            return CompletedProcess(cmd, 0, "container-id\n", "")
        raise AssertionError(f"unexpected docker command: {cmd}")


class ComposeRunRecorder:
    def __init__(self) -> None:
        self.commands: data.DockerCommands = []

    def __call__(
        self,
        cmd: data.DockerCommand,
        *,
        timeout: int = 120,
    ) -> CompletedProcess[str]:
        if timeout < 0:
            raise AssertionError("timeout must be non-negative")
        self.commands.append(cmd)
        prefix_two = cmd[:2]
        prefix_three = cmd[:3]
        if prefix_three == [data.DOCKER, "image", "inspect"]:
            return CompletedProcess(cmd, 0, "[]", "")
        if prefix_three == [data.DOCKER, "inspect", data.CODING_AGENT_CONTAINER]:
            return CompletedProcess(cmd, 0, json.dumps(data.compose_labels()), "")
        if prefix_three == [data.DOCKER, "ps", "-a"]:
            return CompletedProcess(cmd, 0, "", "")
        if prefix_three == [data.DOCKER, "rm", "-f"]:
            return CompletedProcess(cmd, 0, "removed\n", "")
        if prefix_two == [data.DOCKER, "compose"]:
            return CompletedProcess(cmd, 0, "compose-ok\n", "")
        raise AssertionError(f"unexpected compose/docker command: {cmd}")


class MissingFileRecorder:
    def __init__(self) -> None:
        self.commands: data.DockerCommands = []

    def __call__(
        self,
        cmd: data.DockerCommand,
        *,
        timeout: int = 120,
    ) -> CompletedProcess[str]:
        if timeout < 0:
            raise AssertionError("timeout must be non-negative")
        self.commands.append(cmd)
        if cmd[:3] == [data.DOCKER, "ps", "-a"]:
            return CompletedProcess(cmd, 0, f"{data.CODING_AGENT_CONTAINER}\n", "")
        raise AssertionError(f"unexpected compose/docker command: {cmd}")


class DockerScenarios:
    @classmethod
    def build_run_command(cls, manifests_root: Path) -> data.DockerCommand:
        manifest = data.create_manifest(manifests_root, with_system_prompt=True)
        driver = DockerDriver(manifests_root=manifests_root, default_network="agents-net")
        with patch.dict("os.environ", {data.OPENAI_API_KEY: "secret"}, clear=False):
            return driver._build_run_command(  # noqa: SLF001
                manifest,
                container_name=data.CODING_AGENT_CONTAINER,
            )

    @classmethod
    def start_with_capture(
        cls,
        driver: DockerDriver,
        manifest: AgentManifest,
    ) -> tuple[dict[str, Any], data.DockerCommand]:
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=False))
            stack.enter_context(
                patch.object(driver, "status", return_value=data.missing_build_status())
            )
            run_mock = stack.enter_context(
                patch(
                    data.RUN_PATH,
                    return_value=CompletedProcess([], 0, "container-id\n", ""),
                ),
            )
            cmd_result = driver.start(manifest)
            run_command = list(run_mock.call_args.args[0])
        return cmd_result, run_command

    @classmethod
    def manifest_with_passthrough(cls, root: Path) -> AgentManifest:
        manifest = data.create_manifest(root)
        return AgentManifest.from_dict(
            {
                **manifest.to_dict(),
                "runtime": {
                    **manifest.runtime.to_dict(),
                    "env": {data.OPENAI_API_KEY: "manifest-secret", "LOG_LEVEL": "INFO"},
                    "env_passthrough": [data.OPENAI_API_KEY],
                },
            },
            manifest_path=manifest.manifest_path,
        )

    @classmethod
    def restart_with_capture(
        cls,
        driver: DockerDriver,
        manifest: AgentManifest,
    ) -> DockerRunRecorder:
        recorder = DockerRunRecorder()
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=True))
            stack.enter_context(patch(data.RUN_PATH, side_effect=recorder))
            stack.enter_context(
                patch.object(driver, data.STATUS_KEY, return_value=data.missing_build_status())
            )
            driver.restart(manifest)
        return recorder

    @classmethod
    def start_with_build_capture(
        cls,
        driver: DockerDriver,
        manifest: AgentManifest,
    ) -> tuple[dict[str, Any], DockerRunRecorder]:
        recorder = DockerRunRecorder()
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "_container_exists", return_value=False))
            stack.enter_context(
                patch.object(driver, data.STATUS_KEY, return_value=data.missing_build_status())
            )
            stack.enter_context(patch(data.RUN_PATH, side_effect=recorder))
            cmd_result = driver.start(manifest)
        return cmd_result, recorder

    @classmethod
    def run_mux_build(cls, tmpdir: str) -> data.BuildCapture:
        root, manifest, driver = mux_build_context(tmpdir)
        cmd_result, recorder = cls.start_with_build_capture(driver, manifest)
        return cmd_result, recorder.commands, root


class ComposeScenarios:
    @classmethod
    def start_with_capture(cls, root: Path) -> data.ComposeCapture:
        manifest = data.create_manifest(root)
        driver = data.compose_driver(root)
        recorder = ComposeRunRecorder()
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(driver, "status", return_value=data.compose_status_payload())
            )
            stack.enter_context(patch(data.RUN_PATH, side_effect=recorder))
            cmd_result = driver.start(manifest)
        return cmd_result, recorder.commands, data.compose_file(root)

    @classmethod
    def stop_with_capture(
        cls,
        root: Path,
        *,
        remove: bool,
    ) -> data.ComposeCapture:
        data.create_manifest(root)
        driver = data.compose_driver(root)
        compose_path = data.compose_file(root)
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        compose_path.write_text("{}", encoding="utf-8")
        recorder = ComposeRunRecorder()
        with patch(data.RUN_PATH, side_effect=recorder):
            cmd_result = driver.stop("coding_agent", remove=remove)
        return cmd_result, recorder.commands, compose_path

    @classmethod
    def stop_missing_file_with_capture(
        cls,
        root: Path,
    ) -> tuple[DockerDriver, MissingFileRecorder]:
        return data.compose_driver(root), MissingFileRecorder()


def mux_build_context(tmpdir: str) -> tuple[Path, AgentManifest, DockerDriver]:
    root = Path(tmpdir)
    agents_root = root / "agents"
    agents_root.mkdir()
    (root / "Dockerfile.agent_mux_runtime").write_text("FROM scratch\n", encoding="utf-8")
    return (
        root,
        data.create_manifest(agents_root, image=data.MUX_RUNTIME_IMAGE),
        DockerDriver(manifests_root=agents_root, build_context_root=root),
    )
