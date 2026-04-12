from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.orchestra_agents.backends.agent_mux.process.runner import (
    run_agent_mux,
)
from core.orchestra_agents.backends.agent_mux.process.types import AgentMuxRunRequest


@dataclass(frozen=True)
class _EventStub:
    event_id: str
    event_kind: str


def _settings(root_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        state_root=str(root_dir / "state"),
        omniroute_url="http://omniroute:20128",
        llm_route_policy="codex_only",
        default_model="cx/gpt-5.1-codex-mini",
        mcp_servers=(),
        role="worker",
        variant=None,
        engine="codex",
        agent_timeout_seconds=180,
        agent_mux_binary="agent-mux",
        omniroute_api_key="test-key",
    )


def _request(root_dir: Path) -> AgentMuxRunRequest:
    return AgentMuxRunRequest(
        event=_EventStub(event_id="evt-1", event_kind="smoke_test"),
        dispatch_id="dispatch-1",
        artifact_dir=root_dir / "artifacts",
        working_dir="/workspace",
        agent_slug="smoke-agent",
        context_id="ctx-1",
        system_prompt="Reply directly.",
        settings=_settings(root_dir),
        prompt="hello",
        active_context_path=str(root_dir / "active_context.json"),
    )


def _runtime_home_paths(root_dir: Path) -> tuple[Path, Path]:
    runtime_home = root_dir / "state" / "home" / ".agent-mux"
    config_path = runtime_home / "config.toml"
    codex_config_path = root_dir / "state" / "home" / ".codex" / "config.toml"
    return config_path, codex_config_path


def assert_runtime_home(
    *, case: unittest.TestCase, root_dir: Path, result: dict[str, object]
) -> None:
    config_path, codex_config_path = _runtime_home_paths(root_dir)
    _assert_runtime_paths(case, config_path, codex_config_path)
    runtime_config = config_path.read_text(encoding="utf-8")
    codex_config = codex_config_path.read_text(encoding="utf-8")
    case.assertIn("[defaults]", runtime_config)
    case.assertIn('model = "cx/gpt-5.1-codex-mini"', runtime_config)
    case.assertIn("[roles.worker]", runtime_config)
    case.assertIn('env_key = "OMNIROUTE_API_KEY"', codex_config)
    case.assertIn('model = "cx/gpt-5.1-codex-mini"', codex_config)
    case.assertIn('web_search = "disabled"', codex_config)
    case.assertIsNotNone(result.get("process"))


def _assert_runtime_paths(
    case: unittest.TestCase,
    config_path: Path,
    codex_config_path: Path,
) -> None:
    case.assertTrue(config_path.exists())
    case.assertTrue(codex_config_path.exists())
    case.assertTrue((config_path.parent / "prompts" / "worker.md").exists())


class AgentMuxRuntimeHomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_agent_mux_installs_role_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)

            with patch(
                "core.orchestra_agents.backends.agent_mux.process.runner.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=object()),
            ) as create_process:
                result = await run_agent_mux(_request(root_dir))
                create_process.assert_awaited_once()

            assert_runtime_home(case=self, root_dir=root_dir, result=result)

    async def test_minimax_codex_route_closes_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            request = _request(root_dir)
            request.settings.llm_route_policy = "minimax_only"

            with patch(
                "core.orchestra_agents.backends.agent_mux.process.runner.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=object()),
            ):
                result = await run_agent_mux(request)

        stdin_payload = result["stdin_payload"].decode("utf-8")
        self.assertIn('"close_stdin_after_start": true', stdin_payload)
