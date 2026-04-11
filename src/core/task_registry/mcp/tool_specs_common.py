from __future__ import annotations

from typing import Any

JsonDict = dict[str, Any]

TYPE_FIELD = "type"
DESCRIPTION_FIELD = "description"


def tool_spec(name: str, description: str, schema: JsonDict) -> JsonDict:
    return {"name": name, DESCRIPTION_FIELD: description, "inputSchema": schema}


def object_schema(properties: JsonDict, required: list[str] | None = None) -> JsonDict:
    schema: JsonDict = {TYPE_FIELD: "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def string_prop(description: str) -> JsonDict:
    return {TYPE_FIELD: "string", DESCRIPTION_FIELD: description}


def task_id_prop() -> JsonDict:
    return string_prop("Task UUID")


def checklist_item_schema() -> JsonDict:
    return object_schema(
        {
            "label": string_prop("Checklist item text"),
            "checked": {
                TYPE_FIELD: "boolean",
                DESCRIPTION_FIELD: "Whether item is checked",
                "default": False,
            },
        },
        required=["label"],
    )


def artifact_schema() -> JsonDict:
    return object_schema(
        {
            "url": string_prop("Artifact URL or path"),
            "type": string_prop("Artifact type (e.g. 'file', 'link', 'image')"),
            "label": string_prop("Human-readable label"),
        },
        required=["url", "type"],
    )
