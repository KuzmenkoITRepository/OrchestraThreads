from __future__ import annotations

import json
from typing import Any

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "environment-mcp"

JsonDict = dict[str, Any]


class ServerHelpers:
    @staticmethod
    def jsonrpc_result(request_id: Any, result_payload: JsonDict) -> JsonDict:
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result_payload}

    @staticmethod
    def jsonrpc_error(request_id: Any, code: int, message: str) -> JsonDict:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def initialize_result() -> JsonDict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
        }

    @staticmethod
    def resources_result() -> JsonDict:
        return {"resources": []}

    @staticmethod
    def resource_templates_result() -> JsonDict:
        return {"resourceTemplates": []}

    @staticmethod
    def request_arguments(params: Any) -> JsonDict:
        arguments = params.get("arguments") if isinstance(params, dict) else None
        return dict(arguments) if isinstance(arguments, dict) else {}


class Payloads:
    @staticmethod
    def result(payload: JsonDict, *, text: str | None = None) -> JsonDict:
        rendered_text = text or json.dumps(payload, ensure_ascii=False)
        return {
            "structuredContent": payload,
            "content": [{"type": "text", "text": rendered_text}],
        }

    @staticmethod
    def tools_result() -> JsonDict:
        text_schema = {"type": "string"}
        bool_schema = {"type": "boolean"}
        return {
            "tools": [
                _tool(
                    "environment_list",
                    "List isolated environments with status, ports, workspace paths, and service URLs.",
                    {"type": "object", "properties": {}},
                ),
                _tool(
                    "environment_status",
                    "Return detailed status for one isolated environment.",
                    {
                        "type": "object",
                        "properties": {"environment": text_schema},
                        "required": ["environment"],
                    },
                ),
                _tool(
                    "environment_create",
                    "Create and deploy a new isolated environment from a base environment.",
                    {
                        "type": "object",
                        "properties": {
                            "environment": text_schema,
                            "base_environment": text_schema,
                        },
                        "required": ["environment"],
                    },
                ),
                _tool(
                    "environment_deploy",
                    "Deploy or redeploy an existing isolated environment from Vault-backed runtime configuration.",
                    {
                        "type": "object",
                        "properties": {
                            "environment": text_schema,
                            "pull": bool_schema,
                            "deploy_ref": text_schema,
                        },
                        "required": ["environment"],
                    },
                ),
                _tool(
                    "environment_teardown",
                    "Tear down an isolated environment and optionally preserve its Vault secrets.",
                    {
                        "type": "object",
                        "properties": {
                            "environment": text_schema,
                            "force": bool_schema,
                            "keep_secrets": bool_schema,
                        },
                        "required": ["environment"],
                    },
                ),
                _tool(
                    "environment_usage_guide",
                    "Return the embedded agent instructions for safe use of isolated environment lifecycle tools.",
                    {
                        "type": "object",
                        "properties": {
                            "view": {"type": "string", "enum": ["compact", "full"]},
                        },
                    },
                ),
            ]
        }


def _tool(name: str, description: str, input_schema: JsonDict) -> JsonDict:
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
    }
