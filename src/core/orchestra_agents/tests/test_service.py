from __future__ import annotations

import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from typing import cast

from core.orchestra_agents.tests._service_test_fakes import FakeRuntime, public_service_state_fields
from core.orchestra_agents.tests._service_test_harness import (
    ServiceHTTPHarness,
    write_coding_agent_manifest,
)

_service_constants = import_module("core.orchestra_agents.tests._service_test_constants")
COMPOSE_RUNTIME = cast(str, _service_constants.COMPOSE_RUNTIME)
DOCKER_CLI_RUNTIME = cast(str, _service_constants.DOCKER_CLI_RUNTIME)
STATUS_RUNNING = cast(str, _service_constants.STATUS_RUNNING)

_service_support = import_module("core.orchestra_agents.tests._service_test_support")
created_service = _service_support.created_service
research_manifest_yaml = _service_support.research_manifest_yaml
resolved_runtime_name = _service_support.resolved_runtime_name


class ServiceStateContractTests(unittest.TestCase):
    def test_public_fields_match_target_deps(self) -> None:
        self.assertEqual(
            public_service_state_fields(),
            {
                "registry",
                "builder",
                "default_runtime",
                "runtime_selector",
                "manifest_class",
                "lock",
            },
        )


class ServiceCreateRuntimeTests(unittest.TestCase):
    def test_create_uses_compose_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_coding_agent_manifest(root)
            service = created_service(root)

            self.assertIsNone(service.state.runtime_selector)
            self.assertEqual(resolved_runtime_name(service), "ComposeRuntime")

    def test_create_keeps_docker_cli_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_coding_agent_manifest(root)
            service = created_service(root, runtime_name=DOCKER_CLI_RUNTIME)

            self.assertIsNotNone(service.state.runtime_selector)
            self.assertEqual(resolved_runtime_name(service), "DockerCliRuntime")


class _ServiceHTTPBase(unittest.IsolatedAsyncioTestCase):
    selector_runtime_name: str | None = None

    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        write_coding_agent_manifest(self.root)
        self.harness = await ServiceHTTPHarness.create(
            root=self.root,
            selector_runtime_name=self.selector_runtime_name,
        )

    async def asyncTearDown(self) -> None:
        await self.harness.close()
        self.tmpdir.cleanup()


class ServiceHTTPDefaultTests(_ServiceHTTPBase):
    async def test_lists_agents(self) -> None:
        agents = await self.harness.request("GET", "/api/v1/agents")
        agent = agents["agents"][0]
        compose = cast(FakeRuntime, self.harness.compose_runtime)
        docker_cli = cast(FakeRuntime, self.harness.docker_cli_runtime)

        self.assertEqual(agent["slug"], "coding_agent")
        self.assertEqual(agent["runtime"]["runtime_name"], COMPOSE_RUNTIME)
        self.assertEqual(compose.calls.status_calls, ["coding_agent"])
        self.assertEqual(compose.calls.container_name_calls, ["coding_agent"])
        self.assertEqual(docker_cli.calls.status_calls, [])

    async def test_start_builds_spec_before_runtime(self) -> None:
        started = await self.harness.request("POST", "/api/v1/agents/coding_agent/start")
        compose = cast(FakeRuntime, self.harness.compose_runtime)

        self.assertTrue(started["success"])
        self.assertEqual(started["result"]["runtime_name"], COMPOSE_RUNTIME)
        self.assertEqual(compose.calls.started, ["coding_agent"])

    async def test_stop_builds_spec_before_runtime(self) -> None:
        stopped = await self.harness.request(
            "POST",
            "/api/v1/agents/coding_agent/stop",
            {"remove": True},
        )
        compose = cast(FakeRuntime, self.harness.compose_runtime)

        self.assertFalse(stopped["result"][STATUS_RUNNING])
        self.assertTrue(stopped["result"]["removed"])
        self.assertEqual(compose.calls.stopped, [("coding_agent", True)])

    async def test_restart_builds_spec_before_runtime(self) -> None:
        restarted = await self.harness.request("POST", "/api/v1/agents/coding_agent/restart")
        compose = cast(FakeRuntime, self.harness.compose_runtime)

        self.assertTrue(restarted["success"])
        self.assertEqual(compose.calls.restarted, ["coding_agent"])

    async def test_status_builds_spec_before_runtime(self) -> None:
        await self.harness.request("POST", "/api/v1/agents/coding_agent/start")
        self.harness.events.clear()

        status = await self.harness.request("GET", "/api/v1/agents/coding_agent/status")

        self.assertTrue(status["status"][STATUS_RUNNING])
        self.assertEqual(status["status"]["runtime_name"], COMPOSE_RUNTIME)


class ServiceHTTPSelectorTests(_ServiceHTTPBase):
    selector_runtime_name = DOCKER_CLI_RUNTIME

    async def test_selector_can_choose_docker_cli(self) -> None:
        status = await self.harness.request("GET", "/api/v1/agents/coding_agent/status")
        compose = cast(FakeRuntime, self.harness.compose_runtime)
        docker_cli = cast(FakeRuntime, self.harness.docker_cli_runtime)

        self.assertEqual(status["status"]["runtime_name"], DOCKER_CLI_RUNTIME)
        self.assertEqual(compose.calls.status_calls, [])
        self.assertEqual(docker_cli.calls.status_calls, ["coding_agent"])


class ServiceHTTPValidationTests(_ServiceHTTPBase):
    async def test_validates_manifest_payload(self) -> None:
        result = await self.harness.request(
            "POST",
            "/api/v1/manifests/validate",
            {"yaml": research_manifest_yaml()},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["manifest"]["backend"]["type"], "sgr")
