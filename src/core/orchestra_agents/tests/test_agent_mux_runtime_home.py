from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.orchestra_agents.backends.agent_mux.process.runner import run_agent_mux
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


def assert_runtime_home(
    *, case: unittest.TestCase, root_dir: Path, result: dict[str, object]
) -> None:
    runtime_home = root_dir / "state" / "home" / ".agent-mux"
    config_path = runtime_home / "config.toml"
    case.assertTrue(config_path.exists())
    case.assertTrue((runtime_home / "prompts" / "worker.md").exists())
    case.assertIn('"cx/gpt-5.1-codex-mini"', config_path.read_text(encoding="utf-8"))
    case.assertIsNotNone(result.get("process"))


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
