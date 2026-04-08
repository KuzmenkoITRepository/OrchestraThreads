from __future__ import annotations

import json
from dataclasses import dataclass

from environment_mcp.command_runner import AsyncCommandRunner, CommandResult
from environment_mcp.config import EnvironmentMCPConfig
from environment_mcp.environment_state import enrich_environment_rows, environment_payload
from environment_mcp.mcp_protocol import JsonDict


class _ArgumentParser:
    @staticmethod
    def required_text(arguments: JsonDict, field_name: str) -> str:
        normalized = str(arguments.get(field_name) or "").strip()
        if not normalized:
            raise RuntimeError(f"{field_name} is required")
        return normalized

    @staticmethod
    def optional_text(arguments: JsonDict, field_name: str) -> str | None:
        normalized = str(arguments.get(field_name) or "").strip()
        return normalized or None

    @staticmethod
    def optional_bool(arguments: JsonDict, field_name: str) -> bool:
        return bool(arguments.get(field_name))


class _CommandPayloads:
    @staticmethod
    def success(
        *,
        operation: str,
        environment: JsonDict | None = None,
        environments: list[JsonDict] | None = None,
        command_result: CommandResult | None = None,
        metadata: JsonDict | None = None,
    ) -> JsonDict:
        payload: JsonDict = {"ok": True, "operation": operation}
        if environment is not None:
            payload["environment"] = environment
        if environments is not None:
            payload["environments"] = environments
        if metadata is not None:
            payload.update(metadata)
        if command_result is not None:
            payload["command"] = list(command_result.args)
            payload["stdout"] = command_result.stdout
            payload["stderr"] = command_result.stderr
        return payload

    @staticmethod
    def guide(view: str) -> tuple[JsonDict, str]:
        instruction = {
            "ok": True,
            "operation": "environment_usage_guide",
            "view": view,
            "tools": [
                "environment_list",
                "environment_status",
                "environment_create",
                "environment_deploy",
                "environment_teardown",
                "environment_usage_guide",
            ],
            "workflow": [
                "Use environment_create for temporary isolated workspaces.",
                "Use environment_status or environment_list to discover ports, URLs, workspace, and Vault path.",
                "Use environment_deploy after code updates or when redeploying an existing environment.",
                "Use environment_teardown for temporary environments when work is complete.",
            ],
            "must_do": [
                "Use only environment_* MCP tools for environment lifecycle operations.",
                "Prefer non-prod environments for testing and implementation work.",
                "Read returned status metadata before using environment URLs or workspace paths.",
            ],
            "must_not_do": [
                "Do not call docker compose, Vault commands, git worktree, or deploy shell scripts directly.",
                "Do not operate on prod unless the user explicitly requests prod.",
                "Do not tear down protected environments without explicit confirmation and force semantics.",
            ],
        }
        return instruction, _guide_text(view)


@dataclass(frozen=True)
class _TeardownPlan:
    command: tuple[str, ...]
    force: bool
    keep_secrets: bool


class EnvironmentTools:
    def __init__(self, config: EnvironmentMCPConfig, runner: AsyncCommandRunner) -> None:
        self._config = config
        self._runner = runner

    async def environment_list(self, _arguments: JsonDict) -> JsonDict:
        command_result = await _ToolHelpers.run_script(
            self._runner,
            self._config,
            "list-environments.sh",
            "--json",
        )
        rows = _ToolHelpers.list_rows(command_result.stdout)
        return _CommandPayloads.success(
            operation="environment_list",
            environments=enrich_environment_rows(self._config, rows),
            command_result=command_result,
        )

    async def environment_status(self, arguments: JsonDict) -> JsonDict:
        environment_name = _ArgumentParser.required_text(arguments, "environment")
        command_result = await _ToolHelpers.run_script(
            self._runner,
            self._config,
            "list-environments.sh",
            "--json",
        )
        environment = _ToolHelpers.status_payload(
            self._config,
            environment_name,
            _ToolHelpers.list_rows(command_result.stdout),
        )
        return _CommandPayloads.success(
            operation="environment_status",
            environment=environment,
            command_result=command_result,
        )

    async def environment_create(self, arguments: JsonDict) -> JsonDict:
        environment_name = _ArgumentParser.required_text(arguments, "environment")
        base_environment = _ArgumentParser.optional_text(arguments, "base_environment") or "dev"
        command_result = await _ToolHelpers.run_script(
            self._runner,
            self._config,
            "provision-environment.sh",
            environment_name,
            base_environment,
        )
        return _CommandPayloads.success(
            operation="environment_create",
            environment=environment_payload(self._config, environment_name),
            command_result=command_result,
            metadata={"base_environment": base_environment},
        )

    async def environment_deploy(self, arguments: JsonDict) -> JsonDict:
        environment_name = _ArgumentParser.required_text(arguments, "environment")
        command: list[str] = [environment_name]
        pull = _ArgumentParser.optional_bool(arguments, "pull")
        if pull:
            command.append("--pull")
        deploy_ref = _ArgumentParser.optional_text(arguments, "deploy_ref")
        command_result = await _ToolHelpers.run_script(
            self._runner,
            self._config,
            "deploy-env.sh",
            *command,
            extra_env=_ToolHelpers.deploy_ref_env(deploy_ref),
        )
        return _CommandPayloads.success(
            operation="environment_deploy",
            environment=environment_payload(self._config, environment_name),
            command_result=command_result,
            metadata={"pull": pull},
        )

    async def environment_teardown(self, arguments: JsonDict) -> JsonDict:
        environment_name = _ArgumentParser.required_text(arguments, "environment")
        plan = _ToolHelpers.teardown_plan(arguments, environment_name)
        before = environment_payload(self._config, environment_name)
        command_result = await _ToolHelpers.run_script(
            self._runner,
            self._config,
            "teardown-environment.sh",
            *plan.command,
        )
        return _CommandPayloads.success(
            operation="environment_teardown",
            environment=before,
            command_result=command_result,
            metadata={"force": plan.force, "keep_secrets": plan.keep_secrets},
        )

    async def environment_usage_guide(self, arguments: JsonDict) -> JsonDict:
        view = _ArgumentParser.optional_text(arguments, "view") or "compact"
        payload, text = _CommandPayloads.guide(view)
        payload["text"] = text
        return payload


def _guide_text(view: str) -> str:
    lines = [
        "Use only environment_* MCP tools for environment lifecycle operations.",
        "Do not call docker compose, Vault commands, git worktree, or deploy shell scripts directly.",
        "Prefer non-prod environments; use prod only when the user explicitly asks for prod.",
        "Create temporary isolated environments with environment_create.",
        "Inspect ports, URLs, workspace, and Vault path with environment_status or environment_list.",
        "Redeploy existing environments with environment_deploy.",
        "Delete temporary environments with environment_teardown when work is complete.",
    ]
    if view == "full":
        return "\n".join(f"- {line}" for line in lines)
    return lines[0]


class _ToolHelpers:
    @staticmethod
    async def run_script(
        runner: AsyncCommandRunner,
        config: EnvironmentMCPConfig,
        script_name: str,
        *script_args: str,
        extra_env: dict[str, str] | None = None,
    ) -> CommandResult:
        command_result = await runner.run(
            args=("bash", str(config.deploy_dir / script_name), *script_args),
            cwd=config.repo_root,
            env=_ToolHelpers.command_env(config, extra_env),
        )
        if command_result.returncode == 0:
            return command_result
        if command_result.stderr:
            raise RuntimeError(command_result.stderr)
        if command_result.stdout:
            raise RuntimeError(command_result.stdout)
        raise RuntimeError(f"Command failed: {' '.join(command_result.args)}")

    @staticmethod
    def command_env(
        config: EnvironmentMCPConfig,
        extra_env: dict[str, str] | None,
    ) -> dict[str, str]:
        env = {
            "VAULT_ADDR": config.vault_addr,
            "OT_ENVS_ROOT": str(config.envs_root),
        }
        if extra_env is not None:
            env.update(extra_env)
        return env

    @staticmethod
    def deploy_ref_env(deploy_ref: str | None) -> dict[str, str] | None:
        if deploy_ref is None:
            return None
        return {"OT_DEPLOY_REF": deploy_ref}

    @staticmethod
    def list_rows(stdout: str) -> list[JsonDict]:
        payload = json.loads(stdout or "[]")
        if not isinstance(payload, list):
            raise RuntimeError("environment_list returned invalid JSON")
        return [dict(item) for item in payload if isinstance(item, dict)]

    @staticmethod
    def status_payload(
        config: EnvironmentMCPConfig,
        environment_name: str,
        rows: list[JsonDict],
    ) -> JsonDict:
        for row in rows:
            row_name = str(row.get("name") or "").strip()
            if row_name != environment_name:
                continue
            return environment_payload(
                config,
                environment_name,
                status=str(row.get("status") or "stopped"),
                has_workspace=_ToolHelpers.row_has_workspace(row),
            )
        return environment_payload(config, environment_name)

    @staticmethod
    def row_has_workspace(row: JsonDict) -> bool:
        normalized = str(row.get("has_workspace") or "").strip().lower()
        return normalized == "yes"

    @staticmethod
    def teardown_plan(arguments: JsonDict, environment_name: str) -> _TeardownPlan:
        command: list[str] = [environment_name]
        force = _ArgumentParser.optional_bool(arguments, "force")
        keep_secrets = _ArgumentParser.optional_bool(arguments, "keep_secrets")
        if force:
            command.append("--force")
        if keep_secrets:
            command.append("--keep-secrets")
        return _TeardownPlan(tuple(command), force, keep_secrets)
