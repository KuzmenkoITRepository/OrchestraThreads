from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from aiohttp import ClientSession, ClientTimeout, web

from core.orchestra_agents.registry import AgentManifestRegistry
from core.orchestra_agents.tests._service_test_fakes import (
    FakeBuilder,
    FakeRuntime,
    FakeServiceState,
    RuntimeSelector,
)

_service_runtime = import_module("core.orchestra_agents.service.runtime")
_service_constants = import_module("core.orchestra_agents.tests._service_test_constants")
COMPOSE_RUNTIME = cast(str, _service_constants.COMPOSE_RUNTIME)
DOCKER_CLI_RUNTIME = cast(str, _service_constants.DOCKER_CLI_RUNTIME)
OrchestraAgentsService = cast(type[Any], _service_runtime.OrchestraAgentsService)
build_app = _service_runtime.build_app


def write_coding_agent_manifest(root: Path) -> None:
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
  image: agent-image:latest
  command:
    - python
    - -m
    - agent.main
backend:
  type: codex_framework
        """.strip(),
        encoding="utf-8",
    )


def _runtime_selector(
    selected_name: str,
    runtime_map: dict[str, FakeRuntime],
) -> RuntimeSelector:
    return lambda spec, operation, default_runtime: runtime_map[selected_name]


@dataclass
class ServiceHTTPHarness:
    root: Path
    selector_runtime_name: str | None = None
    runner: web.AppRunner | None = None
    session: ClientSession | None = None
    port: int = 0
    service: Any = None
    events: list[str] = field(default_factory=list)
    compose_runtime: FakeRuntime | None = None
    docker_cli_runtime: FakeRuntime | None = None

    @property
    def compose(self) -> FakeRuntime:
        assert self.compose_runtime is not None
        return self.compose_runtime

    @property
    def docker_cli(self) -> FakeRuntime:
        assert self.docker_cli_runtime is not None
        return self.docker_cli_runtime

    @classmethod
    async def create(
        cls,
        *,
        root: Path,
        selector_runtime_name: str | None = None,
    ) -> ServiceHTTPHarness:
        harness = cls(root=root, selector_runtime_name=selector_runtime_name)
        await harness.start()
        return harness

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        assert self.session is not None
        async with self.session.request(
            method,
            f"http://127.0.0.1:{self.port}{path}",
            json=payload,
        ) as response:
            raw = await response.text()
            parsed = json.loads(raw) if raw else {}
            if response.status != expected_status:
                raise AssertionError(f"{method} {path} -> {response.status}: {parsed}")
            return cast(dict[str, Any], parsed)

    async def start(self) -> None:
        self.events = []
        self.compose_runtime = FakeRuntime(COMPOSE_RUNTIME, self.events)
        self.docker_cli_runtime = FakeRuntime(DOCKER_CLI_RUNTIME, self.events)
        runtime_selector = None
        if self.selector_runtime_name is not None:
            runtime_selector = _runtime_selector(
                self.selector_runtime_name,
                {
                    COMPOSE_RUNTIME: self.compose_runtime,
                    DOCKER_CLI_RUNTIME: self.docker_cli_runtime,
                },
            )
        state = FakeServiceState(
            registry=AgentManifestRegistry(manifests_root=self.root),
            builder=FakeBuilder(self.events),
            default_runtime=self.compose_runtime,
            runtime_selector=runtime_selector,
        )
        self.service = OrchestraAgentsService(state)
        self.runner = web.AppRunner(build_app(self.service))
        await self.runner.setup()
        self.port = _free_port()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()
        self.session = ClientSession(timeout=ClientTimeout(total=10))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])
