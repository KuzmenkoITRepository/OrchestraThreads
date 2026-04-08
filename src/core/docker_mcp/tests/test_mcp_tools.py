from __future__ import annotations

import json
from typing import Any, cast
from unittest import TestCase, mock

from core.docker_mcp.mcp_tools import DockerMCPTools


def _tool_payload(result: dict[str, object]) -> dict[str, Any]:
    content = result["content"]
    assert isinstance(content, list)
    item = content[0]
    assert isinstance(item, dict)
    raw_text = str(item.get("text", ""))
    return cast(dict[str, Any], json.loads(raw_text))


class DockerMCPToolsTests(TestCase):
    def test_docker_ps_returns_structured_containers(self) -> None:
        tool = DockerMCPTools()
        process_result = mock.Mock(
            returncode=0,
            stdout='[{"Names":["/orchestra-agent-whiner"],"State":"running"}]',
            stderr="",
        )

        with mock.patch("core.docker_mcp.mcp_tools.docker_api_get", return_value=process_result):
            result = tool.dispatch("docker_ps", {})

        payload = _tool_payload(result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        containers = cast(list[dict[str, Any]], payload["containers"])
        self.assertEqual(containers[0]["Names"][0], "/orchestra-agent-whiner")

    def test_docker_logs_requires_container_name(self) -> None:
        tool = DockerMCPTools()
        result = tool.dispatch("docker_logs", {})
        payload = _tool_payload(result)
        self.assertFalse(payload["ok"])
        self.assertIn("container_name", str(payload["error"]))

    def test_docker_inspect_returns_first_container(self) -> None:
        tool = DockerMCPTools()
        process_result = mock.Mock(
            returncode=0,
            stdout='{"Name":"/orchestra-whiner","State":{"Running":true}}',
            stderr="",
        )

        with mock.patch("core.docker_mcp.mcp_tools.docker_api_get", return_value=process_result):
            result = tool.dispatch("docker_inspect", {"container_name": "orchestra-whiner"})

        payload = _tool_payload(result)
        self.assertTrue(payload["ok"])
        container = cast(dict[str, Any], payload["container"])
        self.assertEqual(container["Name"], "/orchestra-whiner")

    def test_docker_logs_decodes_raw_stream_payload(self) -> None:
        tool = DockerMCPTools()
        frame = b"\x01\x00\x00\x00\x00\x00\x00\x05hello"
        process_result = mock.Mock(returncode=0, stdout=frame, stderr=b"")

        with mock.patch(
            "core.docker_mcp.mcp_tools.docker_api_get_bytes", return_value=process_result
        ):
            result = tool.dispatch("docker_logs", {"container_name": "orchestra-whiner", "tail": 5})

        payload = _tool_payload(result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["logs"], "hello")
