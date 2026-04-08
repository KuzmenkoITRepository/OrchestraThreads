from __future__ import annotations


def list_task_query(
    *,
    status: str | None,
    assignee: str | None,
    created_by: str | None,
    limit: int,
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    query_args: list[object] = []
    _append_filter(conditions, query_args, column_name="status", field_value=status)
    _append_filter(conditions, query_args, column_name="assignee", field_value=assignee)
    _append_filter(conditions, query_args, column_name="created_by", field_value=created_by)
    query_args.append(max(1, limit))
    where_clause = _where_clause(conditions)
    limit_index = len(query_args)
    query = (
        "SELECT * FROM tasks"
        f"{where_clause}"
        " ORDER BY updated_at DESC, created_at DESC"
        f" LIMIT ${limit_index}"
    )
    return query, query_args


def _append_filter(
    conditions: list[str],
    query_args: list[object],
    *,
    column_name: str,
    field_value: object | None,
) -> None:
    if field_value is None:
        return
    query_args.append(field_value)
    conditions.append(f"{column_name} = ${len(query_args)}")


def _where_clause(conditions: list[str]) -> str:
    if not conditions:
        return ""
    joined_conditions = " AND ".join(conditions)
    return f" WHERE {joined_conditions}"
