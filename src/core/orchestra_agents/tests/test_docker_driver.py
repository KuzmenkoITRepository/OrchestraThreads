from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.manifest import AgentManifest


def _manifest_payload() -> dict:
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


class DockerDriverTests(unittest.TestCase):
    def test_build_run_command_includes_standard_env_and_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifests_root = Path(tmpdir)
            agent_dir = manifests_root / "coding_agent"
            agent_dir.mkdir()
            manifest_path = agent_dir / "manifest.yaml"
            manifest_path.write_text("{}", encoding="utf-8")
            (agent_dir / "system_prompt.md").write_text("prompt", encoding="utf-8")
            manifest = AgentManifest.from_dict(_manifest_payload(), manifest_path=manifest_path)
            driver = DockerDriver(manifests_root=manifests_root, default_network="agents-net")

            with patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=False):
                command = driver._build_run_command(manifest, container_name="orchestra-agent-coding_agent")  # noqa: SLF001

            rendered = " ".join(command)
            self.assertIn("--network agents-net", rendered)
            self.assertIn("ORCHESTRA_AGENT_MANIFEST=/orchestra/agents/coding_agent/manifest.yaml", rendered)
            self.assertIn("ORCHESTRA_AGENT_BACKEND_TYPE=codex_framework", rendered)
            self.assertIn("--health-cmd", rendered)
            self.assertIn("127.0.0.1:8787/healthz", rendered)
            self.assertIn("OPENAI_API_KEY=secret", rendered)
            self.assertIn("agent-image:latest", rendered)

    def test_status_combines_docker_and_health(self) -> None:
        manifest = AgentManifest.from_dict(_manifest_payload())
        driver = DockerDriver(manifests_root="/tmp")
        state = {"Running": True, "Status": "running", "StartedAt": "2025-01-01T00:00:00Z", "Error": ""}
        with patch("core.orchestra_agents.docker_driver._run", return_value=CompletedProcess([], 0, json.dumps(state), "")):
            with patch.object(driver, "_probe_health", return_value={"ok": True, "payload": {"status": "ok"}}):
                status = driver.status(manifest)

        self.assertTrue(status["exists"])
        self.assertTrue(status["running"])
        self.assertTrue(status["healthy"])
        self.assertEqual(status["docker_status"], "running")

    def test_start_uses_docker_run_for_new_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifests_root = Path(tmpdir)
            agent_dir = manifests_root / "coding_agent"
            agent_dir.mkdir()
            manifest_path = agent_dir / "manifest.yaml"
            manifest_path.write_text("{}", encoding="utf-8")
            manifest = AgentManifest.from_dict(_manifest_payload(), manifest_path=manifest_path)
            driver = DockerDriver(manifests_root=manifests_root)

            with patch.object(driver, "_container_exists", return_value=False):
                with patch.object(driver, "status", return_value={"exists": True, "running": True, "healthy": False}):
                    with patch(
                        "core.orchestra_agents.docker_driver._run",
                        return_value=CompletedProcess([], 0, "container-id\n", ""),
                    ) as run_mock:
                        result = driver.start(manifest)

            self.assertTrue(result["exists"])
            self.assertTrue(run_mock.call_args.args[0][:3] == ["docker", "run", "-d"])

    def test_start_builds_known_local_runtime_image_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifests_root = root / "agents"
            manifests_root.mkdir()
            agent_dir = manifests_root / "coding_agent"
            agent_dir.mkdir()
            manifest_path = agent_dir / "manifest.yaml"
            manifest_path.write_text("{}", encoding="utf-8")
            (root / "Dockerfile.agent_mux_runtime").write_text("FROM scratch\n", encoding="utf-8")

            payload = _manifest_payload()
            payload["runtime"]["image"] = "orchestra-agent-mux-runtime:latest"
            manifest = AgentManifest.from_dict(payload, manifest_path=manifest_path)
            driver = DockerDriver(manifests_root=manifests_root, build_context_root=root)
            commands: list[list[str]] = []

            def fake_run(cmd: list[str], *, timeout: int = 120) -> CompletedProcess[str]:
                commands.append(cmd)
                if cmd[:3] == ["docker", "image", "inspect"]:
                    return CompletedProcess(cmd, 1, "", "image not found")
                if cmd[:2] == ["docker", "build"]:
                    return CompletedProcess(cmd, 0, "built", "")
                if cmd[:3] == ["docker", "run", "-d"]:
                    return CompletedProcess(cmd, 0, "container-id\n", "")
                raise AssertionError(f"unexpected docker command: {cmd}")

            with patch.object(driver, "_container_exists", return_value=False):
                with patch.object(driver, "status", return_value={"exists": True, "running": True, "healthy": False}):
                    with patch("core.orchestra_agents.docker_driver._run", side_effect=fake_run):
                        result = driver.start(manifest)

            self.assertTrue(result["exists"])
            self.assertEqual(commands[0][:3], ["docker", "image", "inspect"])
            self.assertEqual(commands[1][:2], ["docker", "build"])
            self.assertIn(str(root / "Dockerfile.agent_mux_runtime"), commands[1])
            self.assertEqual(commands[2][:3], ["docker", "run", "-d"])
