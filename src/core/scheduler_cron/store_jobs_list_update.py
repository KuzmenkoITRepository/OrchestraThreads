from __future__ import annotations

from core.scheduler_cron import common as scheduler_common
from core.scheduler_cron.store_jobs_types import SqlTuple


def jobs_list_query(
    enabled: bool | None,
    job_type: str | None,
    limit: int,
) -> SqlTuple:
    args: list[object] = []
    where_parts = ["1=1"]
    if enabled is not None:
        args.append(enabled)
        where_parts.append(f"enabled = ${len(args)}")
    if job_type is not None:
        args.append(
            scheduler_common.ensure_choice(
                job_type,
                field="job_type",
                allowed=scheduler_common.JOB_TYPES,
            )
        )
        where_parts.append(f"job_type = ${len(args)}")
    args.append(_normalized_limit(limit))
    where_clause = " AND ".join(where_parts)
    limit_index = len(args)
    query = f"SELECT * FROM scheduler_jobs WHERE {where_clause} ORDER BY created_at DESC LIMIT ${limit_index}"
    return query, args


class _UpdateBuilder:
    def __init__(self, changes: dict[str, object]) -> None:
        _validate_update_fields(changes)
        self._changes = changes

    def statement(self, name: str) -> SqlTuple:
        assignments, args = self._build_update_parts()
        assignments.append("updated_at = NOW()")
        name_index = self._append_name(args, name)
        query = self._update_query(assignments, name_index)
        return query, args

    def _build_update_parts(self) -> tuple[list[str], list[object]]:
        args: list[object] = []
        assignments: list[str] = []
        for index, (field_name, field_value) in enumerate(self._changes.items(), start=1):
            args.append(_normalize_update_value(field_name, field_value))
            assignments.append(f"{field_name} = ${index}")
        return assignments, args

    def _append_name(self, args: list[object], name: str) -> int:
        args.append(name.strip())
        return len(args)

    def _update_query(self, assignments: list[str], name_index: int) -> str:
        assignments_text = ", ".join(assignments)
        return f"UPDATE scheduler_jobs SET {assignments_text} WHERE name = ${name_index}"


def update_job_statement(name: str, changes: dict[str, object]) -> SqlTuple:
    update_builder = _UpdateBuilder(changes)
    return update_builder.statement(name)


def _normalized_limit(limit: int) -> int:
    return max(1, int(limit or scheduler_common.DEFAULT_LIST_LIMIT))


def _validate_update_fields(changes: dict[str, object]) -> None:
    allowed_fields = {
        "schedule",
        "action_type",
        "action_payload",
        "enabled",
        "auto_delete",
        "misfire_policy",
        "last_run_at",
        "next_run_at",
        "run_count",
        "failure_count",
        "metadata",
    }
    unknown = sorted(set(changes) - allowed_fields)
    if unknown:
        text = ", ".join(unknown)
        raise scheduler_common.SchedulerCronError(f"Unknown job update fields: {text}")


def _normalize_update_value(field_name: str, field_value: object) -> object:
    if field_name == "action_type" and field_value is not None:
        return scheduler_common.ensure_choice(
            str(field_value),
            field="action_type",
            allowed=scheduler_common.ACTION_TYPES,
        )
    if field_name == "misfire_policy" and field_value is not None:
        return scheduler_common.ensure_choice(
            str(field_value),
            field="misfire_policy",
            allowed=scheduler_common.MISFIRE_POLICIES,
        )
    return field_value
