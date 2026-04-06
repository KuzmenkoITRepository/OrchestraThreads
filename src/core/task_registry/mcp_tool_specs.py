from __future__ import annotations

from typing import Any

JsonDict = dict[str, Any]


def _tool(name: str, description: str, schema: JsonDict) -> JsonDict:
    return {"name": name, "description": description, "inputSchema": schema}


def _object_schema(  # noqa: WPS210  # Schema builder needs properties + required lists.
    properties: JsonDict,
    required: list[str] | None = None,
) -> JsonDict:
    schema: JsonDict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


_CHECKLIST_ITEM_SCHEMA: JsonDict = {  # noqa: WPS407  # Schema dict must be mutable for JSON serialization.
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Checklist item text"},
        "checked": {"type": "boolean", "description": "Whether item is checked", "default": False},
    },
    "required": ["label"],
}

_ARTIFACT_SCHEMA: JsonDict = {  # noqa: WPS407  # Schema dict must be mutable for JSON serialization.
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Artifact URL or path"},
        "type": {"type": "string", "description": "Artifact type (e.g. 'file', 'link', 'image')"},
        "label": {"type": "string", "description": "Human-readable label"},
    },
    "required": ["url", "type"],
}

_TASK_ID_PROP: JsonDict = {"type": "string", "description": "Task UUID"}  # noqa: WPS407


def tool_specs() -> list[JsonDict]:  # noqa: WPS213  # All 10 specs belong in one list.
    return [
        _tool(
            "task_create",
            "Create a new task with optional description, acceptance criteria, and checklist.",
            _object_schema(
                {
                    "title": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Task description"},
                    "acceptance_criteria": {"type": "string", "description": "Acceptance criteria"},
                    "created_by": {"type": "string", "description": "Creator agent name"},
                    "status": {
                        "type": "string",
                        "description": "Initial status",
                        "default": "draft",
                    },
                    "assignee": {"type": "string", "description": "Assigned agent name"},
                    "priority": {
                        "type": "string",
                        "description": "Priority level",
                        "default": "normal",
                    },
                    "checklist": {
                        "type": "array",
                        "items": _CHECKLIST_ITEM_SCHEMA,
                        "description": "Initial checklist items",
                    },
                },
                required=["title", "created_by"],
            ),
        ),
        _tool(
            "task_get",
            "Get a task by its ID with full details.",
            _object_schema(
                {"task_id": _TASK_ID_PROP},
                required=["task_id"],
            ),
        ),
        _tool(
            "task_list",
            "List tasks with optional filters by status, assignee, or creator.",
            _object_schema(
                {
                    "status": {"type": "string", "description": "Filter by status"},
                    "assignee": {"type": "string", "description": "Filter by assignee"},
                    "created_by": {"type": "string", "description": "Filter by creator"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return",
                        "default": 100,
                    },
                },
            ),
        ),
        _tool(
            "task_update_status",
            "Update the status of an existing task.",
            _object_schema(
                {
                    "task_id": _TASK_ID_PROP,
                    "status": {"type": "string", "description": "New status value"},
                },
                required=["task_id", "status"],
            ),
        ),
        _tool(
            "task_assign",
            "Assign a task to an agent.",
            _object_schema(
                {
                    "task_id": _TASK_ID_PROP,
                    "assignee": {"type": "string", "description": "Agent name to assign"},
                },
                required=["task_id", "assignee"],
            ),
        ),
        _tool(
            "task_add_comment",
            "Add a comment to a task.",
            _object_schema(
                {
                    "task_id": _TASK_ID_PROP,
                    "author": {"type": "string", "description": "Comment author"},
                    "body": {"type": "string", "description": "Comment text"},
                    "artifacts": {
                        "type": "array",
                        "items": _ARTIFACT_SCHEMA,
                        "description": "Optional attachments",
                    },
                },
                required=["task_id", "author", "body"],
            ),
        ),
        _tool(
            "task_add_artifact",
            "Add an artifact (file, link, image) to a task.",
            _object_schema(
                {
                    "task_id": _TASK_ID_PROP,
                    "artifact": {
                        **_ARTIFACT_SCHEMA,
                        "description": "Artifact object with url, type, and optional label",
                    },
                },
                required=["task_id", "artifact"],
            ),
        ),
        _tool(
            "task_link_thread",
            "Link an orchestra thread to a task.",
            _object_schema(
                {
                    "task_id": _TASK_ID_PROP,
                    "thread_id": {
                        "type": "string",
                        "format": "uuid",
                        "description": "Thread UUID to link",
                    },
                },
                required=["task_id", "thread_id"],
            ),
        ),
        _tool(
            "task_get_checklist",
            "Get all checklist items for a task.",
            _object_schema(
                {"task_id": _TASK_ID_PROP},
                required=["task_id"],
            ),
        ),
        _tool(
            "task_update_checklist",
            "Update a checklist item's checked state.",
            _object_schema(
                {
                    "item_id": {"type": "string", "description": "Checklist item UUID"},
                    "checked": {"type": "boolean", "description": "New checked state"},
                    "checked_by": {"type": "string", "description": "Agent who checked/unchecked"},
                },
                required=["item_id", "checked", "checked_by"],
            ),
        ),
    ]
