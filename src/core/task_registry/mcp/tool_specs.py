from __future__ import annotations

from core.task_registry.mcp import tool_specs_common as _common

DESCRIPTION_FIELD = _common.DESCRIPTION_FIELD
TYPE_FIELD = _common.TYPE_FIELD
JsonDict = _common.JsonDict
artifact_schema = _common.artifact_schema
checklist_item_schema = _common.checklist_item_schema
object_schema = _common.object_schema
string_prop = _common.string_prop
task_id_prop = _common.task_id_prop
tool_spec = _common.tool_spec

TASK_ID_FIELD = "task_id"
STATUS_FIELD = "status"
ASSIGNEE_FIELD = "assignee"


def _task_lifecycle_specs() -> list[JsonDict]:
    return [
        tool_spec(
            "task_create",
            "Create a new task with optional description, acceptance criteria, and checklist.",
            object_schema(
                {
                    "title": string_prop("Task title"),
                    "description": string_prop("Task description"),
                    "acceptance_criteria": string_prop("Acceptance criteria"),
                    "created_by": string_prop("Creator agent name"),
                    STATUS_FIELD: {
                        TYPE_FIELD: "string",
                        DESCRIPTION_FIELD: "Initial status",
                        "default": "draft",
                    },
                    ASSIGNEE_FIELD: string_prop("Assigned agent name"),
                    "priority": {
                        TYPE_FIELD: "string",
                        DESCRIPTION_FIELD: "Priority level",
                        "default": "normal",
                    },
                    "checklist": {
                        TYPE_FIELD: "array",
                        "items": checklist_item_schema(),
                        DESCRIPTION_FIELD: "Initial checklist items",
                    },
                    "artifacts": {
                        TYPE_FIELD: "array",
                        "items": artifact_schema(),
                        DESCRIPTION_FIELD: "Initial artifacts attached to the task",
                    },
                },
                required=["title", "created_by"],
            ),
        ),
        tool_spec(
            "task_get",
            "Get a task by its ID with full details.",
            object_schema({TASK_ID_FIELD: task_id_prop()}, required=[TASK_ID_FIELD]),
        ),
        tool_spec(
            "task_list",
            "List tasks with optional filters by status, assignee, or creator.",
            object_schema(
                {
                    STATUS_FIELD: string_prop("Filter by status"),
                    ASSIGNEE_FIELD: string_prop("Filter by assignee"),
                    "created_by": string_prop("Filter by creator"),
                    "limit": {
                        TYPE_FIELD: "integer",
                        DESCRIPTION_FIELD: "Max results to return",
                        "default": 100,
                    },
                }
            ),
        ),
        tool_spec(
            "task_update_status",
            "Update the status of an existing task.",
            object_schema(
                {
                    TASK_ID_FIELD: task_id_prop(),
                    STATUS_FIELD: string_prop("New status value"),
                },
                required=[TASK_ID_FIELD, STATUS_FIELD],
            ),
        ),
        tool_spec(
            "task_assign",
            "Assign a task to an agent.",
            object_schema(
                {
                    TASK_ID_FIELD: task_id_prop(),
                    ASSIGNEE_FIELD: string_prop("Agent name to assign"),
                },
                required=[TASK_ID_FIELD, ASSIGNEE_FIELD],
            ),
        ),
    ]


def _task_update_specs() -> list[JsonDict]:
    return [
        tool_spec(
            "task_add_comment",
            "Add a comment to a task.",
            object_schema(
                {
                    TASK_ID_FIELD: task_id_prop(),
                    "author": string_prop("Comment author"),
                    "body": string_prop("Comment text"),
                    "artifacts": {
                        "type": "array",
                        "items": artifact_schema(),
                        "description": "Optional attachments",
                    },
                },
                required=[TASK_ID_FIELD, "author", "body"],
            ),
        ),
        tool_spec(
            "task_add_artifact",
            "Add an artifact (file, link, image) to a task.",
            object_schema(
                {
                    TASK_ID_FIELD: task_id_prop(),
                    "artifact": {
                        **artifact_schema(),
                        DESCRIPTION_FIELD: "Artifact object with url, type, and optional label",
                    },
                },
                required=[TASK_ID_FIELD, "artifact"],
            ),
        ),
        tool_spec(
            "task_link_thread",
            "Link an orchestra thread to a task.",
            object_schema(
                {
                    TASK_ID_FIELD: task_id_prop(),
                    "thread_id": {
                        TYPE_FIELD: "string",
                        "format": "uuid",
                        DESCRIPTION_FIELD: "Thread UUID to link",
                    },
                },
                required=[TASK_ID_FIELD, "thread_id"],
            ),
        ),
        tool_spec(
            "task_get_checklist",
            "Get all checklist items for a task.",
            object_schema({TASK_ID_FIELD: task_id_prop()}, required=[TASK_ID_FIELD]),
        ),
        tool_spec(
            "task_update_checklist",
            "Update a checklist item's checked state.",
            object_schema(
                {
                    "item_id": string_prop("Checklist item UUID"),
                    "checked": {
                        TYPE_FIELD: "boolean",
                        DESCRIPTION_FIELD: "New checked state",
                    },
                    "checked_by": string_prop("Agent who checked/unchecked"),
                },
                required=["item_id", "checked", "checked_by"],
            ),
        ),
    ]


def tool_specs() -> list[JsonDict]:
    return [
        *_task_lifecycle_specs(),
        *_task_update_specs(),
    ]
