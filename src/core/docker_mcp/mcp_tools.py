from __future__ import annotations

import json
import logging
from typing import Any

from core.docker_mcp.log_decode import (
    bytes_output,
    command_output,
    containers_payload,
    decode_logs_output,
)
from core.docker_mcp.socket_api import docker_api_get, docker_api_get_bytes, logs_path

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]
_DEFAULT_TAIL_LINES = 100


def _text_result(payload: JsonDict) -> JsonDict:
    rendered = json.dumps(payload, ensure_ascii=False)
    return {"content": [{"type": "text", "text": rendered}]}


def _require_string(arguments: JsonDict, field: str) -> str:
    value = str(arguments.get(field) or "").strip()
    if not value:
        raise ValueError(f"Missing required parameter: {field}")
    return value


def _to_tail(arguments: JsonDict) -> int:
    raw_tail = arguments.get("tail", _DEFAULT_TAIL_LINES)
    try:
        tail = int(raw_tail)
    except (TypeError, ValueError):
        return _DEFAULT_TAIL_LINES
    return max(1, tail)


class DockerMCPTools:
    def dispatch(self, name: str, arguments: JsonDict) -> JsonDict:
        handlers = {
            "docker_ps": self._docker_ps,
            "docker_logs": self._docker_logs,
            "docker_inspect": self._docker_inspect,
        }
        handler = handlers.get(name)
        if handler is None:
            return _text_result({"ok": False, "error": f"Unknown tool: {name}"})
        try:
            return handler(arguments)
        except Exception as exc:
            logger.error("Docker MCP tool %s failed: %s", name, exc, exc_info=True)
            return _text_result({"ok": False, "error": str(exc)})

    def _docker_ps(self, arguments: JsonDict) -> JsonDict:
        all_flag = 1 if bool(arguments.get("all")) else 0
        result = docker_api_get(f"/containers/json?all={all_flag}")
        if result.returncode != 0:
            return _text_result({"ok": False, "error": command_output(result)})
        containers = containers_payload(result.stdout)
        return _text_result({"ok": True, "containers": containers, "count": len(containers)})

    def _docker_logs(self, arguments: JsonDict) -> JsonDict:
        container_name = _require_string(arguments, "container_name")
        path = logs_path(container_name, tail=_to_tail(arguments), since=arguments.get("since"))
        result = docker_api_get_bytes(path)
        if result.returncode != 0:
            return _text_result({"ok": False, "error": bytes_output(result)})
        return _text_result(
            {
                "ok": True,
                "container_name": container_name,
                "logs": decode_logs_output(result.stdout),
            }
        )

    def _docker_inspect(self, arguments: JsonDict) -> JsonDict:
        container_name = _require_string(arguments, "container_name")
        from core.docker_mcp.socket_api import container_path

        result = docker_api_get(f"/containers/{container_path(container_name)}/json")
        if result.returncode != 0:
            return _text_result({"ok": False, "error": command_output(result)})
        item = json.loads(result.stdout or "{}")
        return _text_result({"ok": True, "container": item})
