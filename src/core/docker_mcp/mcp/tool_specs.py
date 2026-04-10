from __future__ import annotations

from typing import Any

JsonDict = dict[str, Any]


def _tool(name: str, description: str, schema: JsonDict) -> JsonDict:
    return {"name": name, "description": description, "inputSchema": schema}


def _object_schema(properties: JsonDict, required: list[str] | None = None) -> JsonDict:
    schema: JsonDict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def tool_specs() -> list[JsonDict]:
    return [
        _tool(
            "docker_ps",
            "List running or all Docker containers.",
            _object_schema(
                {
                    "all": {
                        "type": "boolean",
                        "description": "Include stopped containers.",
                        "default": False,
                    }
                }
            ),
        ),
        _tool(
            "docker_logs",
            "Read recent logs for a Docker container.",
            _object_schema(
                {
                    "container_name": {
                        "type": "string",
                        "description": "Container name or ID.",
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Number of recent lines to include.",
                        "default": 100,
                    },
                    "since": {
                        "type": "string",
                        "description": "Optional docker --since value.",
                    },
                },
                required=["container_name"],
            ),
        ),
        _tool(
            "docker_inspect",
            "Inspect a Docker container and return structured metadata.",
            _object_schema(
                {
                    "container_name": {
                        "type": "string",
                        "description": "Container name or ID.",
                    }
                },
                required=["container_name"],
            ),
        ),
    ]
