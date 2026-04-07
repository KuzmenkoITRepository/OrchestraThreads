from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from environment_mcp.command_runner import CommandResult
from environment_mcp.config import EnvironmentMCPConfig
from environment_mcp.mcp_server import EnvironmentMCPServer


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.results: dict[str, CommandResult] = {}

    async def run(
        self,
        *,
        args: tuple[str, ...],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert cwd
        assert env is None or isinstance(env, dict)
        self.calls.append(tuple(args))
        return self.results[Path(args[1]).name]


class EnvironmentMCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repo_root = Path(tempfile.mkdtemp(prefix="environment_mcp_repo_"))
        self.deploy_dir = self.repo_root / "deploy"
        self.deploy_dir.mkdir(parents=True)
        self.envs_root = self.repo_root / "environments"
        self.envs_root.mkdir()
        self.config = EnvironmentMCPConfig(
            repo_root=self.repo_root,
            deploy_dir=self.deploy_dir,
            envs_root=self.envs_root,
            vault_addr="http://127.0.0.1:8200",
        )
        self.runner = _FakeRunner()
        self.server = EnvironmentMCPServer(config=self.config, runner=self.runner)

    async def test_tools_list_exposes_environment_tools(self) -> None:
        response = await self.server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert response is not None
        tools = response["result"]["tools"]
        tool_names = {item["name"] for item in tools}
        self.assertIn("environment_create", tool_names)
        self.assertIn("environment_usage_guide", tool_names)

    async def test_usage_guide_returns_embedded_text(self) -> None:
        result = await self.server.handle_tools_call(
            name="environment_usage_guide",
            arguments={"view": "full"},
        )
        structured = result["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["operation"], "environment_usage_guide")
        self.assertIn("environment_create", structured["tools"])
        self.assertIn("Use only environment_* MCP tools", result["content"][0]["text"])

    async def test_environment_list_enriches_paths_and_ports(self) -> None:
        env_dir = self.envs_root / "qa"
        workspace_dir = env_dir / "workspace"
        workspace_dir.mkdir(parents=True)
        (env_dir / "ports.env").write_text(
            "OT_PORT_THREADS=30123\nOT_PORT_AGENTS=30125\n",
            encoding="utf-8",
        )
        self.runner.results["list-environments.sh"] = CommandResult(
            args=("bash", str(self.deploy_dir / "list-environments.sh"), "--json"),
            returncode=0,
            stdout='[{"name":"qa","status":"running","port_threads":"30123","has_workspace":"yes"}]',
            stderr="",
        )

        result = await self.server.handle_tools_call(name="environment_list", arguments={})
        environment = result["structuredContent"]["environments"][0]

        self.assertEqual(environment["name"], "qa")
        self.assertEqual(environment["status"], "running")
        self.assertEqual(environment["ports"]["OT_PORT_THREADS"], "30123")
        self.assertTrue(environment["workspace_exists"])
        self.assertEqual(environment["urls"]["threads"], "http://127.0.0.1:30123")

    async def test_environment_create_invokes_provision_script(self) -> None:
        env_dir = self.envs_root / "sandbox"
        (env_dir / "workspace").mkdir(parents=True)
        self.runner.results["provision-environment.sh"] = CommandResult(
            args=(
                "bash",
                str(self.deploy_dir / "provision-environment.sh"),
                "sandbox",
                "dev",
            ),
            returncode=0,
            stdout="Environment provisioned successfully",
            stderr="",
        )

        result = await self.server.handle_tools_call(
            name="environment_create",
            arguments={"environment": "sandbox", "base_environment": "dev"},
        )

        structured = result["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["base_environment"], "dev")
        self.assertEqual(structured["environment"]["name"], "sandbox")
        self.assertIn("provision-environment.sh", self.runner.calls[0][1])

    async def test_environment_deploy_passes_pull_flag(self) -> None:
        self.runner.results["deploy-env.sh"] = CommandResult(
            args=("bash", str(self.deploy_dir / "deploy-env.sh"), "qa", "--pull"),
            returncode=0,
            stdout="Deployed environment qa",
            stderr="",
        )

        result = await self.server.handle_tools_call(
            name="environment_deploy",
            arguments={"environment": "qa", "pull": True},
        )

        self.assertTrue(result["structuredContent"]["pull"])
        self.assertEqual(self.runner.calls[0][-1], "--pull")
