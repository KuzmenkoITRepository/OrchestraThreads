from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from core.orchestra_agents.registry import AgentManifestRegistry
from core.orchestra_agents.service import OrchestraAgentsService, build_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class FakeDriver:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[tuple[str, bool]] = []
        self.restarted: list[str] = []

    def container_name(self, slug: str) -> str:
        return f"orchestra-agent-{slug}"

    def status(self, manifest) -> dict[str, Any]:
        return {
            "slug": manifest.slug,
            "container_name": self.container_name(manifest.slug),
            "exists": True,
            "running": manifest.slug in self.started or manifest.slug in self.restarted,
            "healthy": True,
            "backend_type": manifest.backend.type,
            "http_endpoint": manifest.resolve_http_endpoint(
                container_name=self.container_name(manifest.slug)
            ),
            "docker_status": "running",
            "health_status": {"ok": True},
            "started_at": "2025-01-01T00:00:00Z",
            "last_error": None,
        }

    def start(self, manifest) -> dict[str, Any]:
        self.started.append(manifest.slug)
        return self.status(manifest)

    def stop(self, slug: str, *, remove: bool = False) -> dict[str, Any]:
        self.stopped.append((slug, remove))
        return {
            "slug": slug,
            "container_name": self.container_name(slug),
            "exists": not remove,
            "running": False,
            "removed": remove,
        }

    def restart(self, manifest) -> dict[str, Any]:
        self.restarted.append(manifest.slug)
        return self.status(manifest)


class ServiceHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        agent_dir = root / "coding_agent"
        agent_dir.mkdir()
        (agent_dir / "manifest.yaml").write_text(
            """
slug: coding_agent
display_name: Coding Agent
status: active
agent:
  working_dir: /workspace
  http_endpoint: http://orchestra-agent-coding_agent:8787
  system_prompt_file: system_prompt.md
runtime:
  driver: docker
  image: agent-image:latest
backend:
  type: codex_framework
            """.strip(),
            encoding="utf-8",
        )
        self.driver = FakeDriver()
        self.service = OrchestraAgentsService(
            registry=AgentManifestRegistry(manifests_root=root),
            driver=self.driver,
        )
        app = build_app(self.service)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.port = _free_port()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.runner.cleanup()
        self.tmpdir.cleanup()

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        async with self.session.request(
            method, f"http://127.0.0.1:{self.port}{path}", json=payload
        ) as response:
            raw = await response.text()
            data = json.loads(raw) if raw else {}
            if response.status != expected_status:
                raise AssertionError(f"{method} {path} -> {response.status}: {data}")
            return data

    async def test_lists_and_starts_agents(self) -> None:
        agents = await self._request("GET", "/api/v1/agents")
        self.assertEqual(agents["count"], 1)
        self.assertEqual(agents["agents"][0]["slug"], "coding_agent")

        started = await self._request("POST", "/api/v1/agents/coding_agent/start")
        self.assertTrue(started["success"])
        self.assertEqual(self.driver.started, ["coding_agent"])

        status = await self._request("GET", "/api/v1/agents/coding_agent/status")
        self.assertTrue(status["status"]["running"])

    async def test_validates_manifest_payload(self) -> None:
        result = await self._request(
            "POST",
            "/api/v1/manifests/validate",
            {
                "yaml": """
slug: research_agent
display_name: Research Agent
status: active
agent:
  working_dir: /workspace
  http_endpoint: http://orchestra-agent-research_agent:8787
runtime:
  driver: docker
  image: agent-image:latest
backend:
  type: sgr
                """.strip()
            },
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["manifest"]["backend"]["type"], "sgr")
