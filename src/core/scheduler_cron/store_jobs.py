from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any, Protocol, cast


class _CommonModule(Protocol):
    ACTION_TYPES: tuple[str, ...]
    DEFAULT_LIST_LIMIT: int
    JOB_TYPES: tuple[str, ...]
    MISFIRE_POLICIES: tuple[str, ...]
    SchedulerCronError: type[Exception]

    def ensure_choice(self, value: str, *, field: str, allowed: tuple[str, ...]) -> str: ...


class _BaseModule(Protocol):
    def row_to_dict(self, row: Any) -> dict[str, object] | None: ...


_common_module = cast(_CommonModule, import_module("core.scheduler_cron.common"))
_base_module = cast(_BaseModule, import_module("core.scheduler_cron.store_base"))


class _PoolOwner(Protocol):
    pool: Any


def _normalize_limit(limit: int, default_limit: int) -> int:
    return max(1, int(limit or default_limit))


def _query_for_list(filters: list[str], args_length: int) -> str:
    query = "SELECT * FROM scheduler_jobs"
    if filters:
        query += " WHERE " + " AND ".join(filters)
    return f"{query} ORDER BY created_at DESC LIMIT ${args_length}"


def _allowed_update_keys() -> set[str]:
    keys = (
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
    )
    return set(keys)


def _validate_update_keys(changes: dict[str, object]) -> None:
    unknown = sorted(set(changes) - _allowed_update_keys())
    if unknown:
        raise _common_module.SchedulerCronError(f"Unknown job update fields: {', '.join(unknown)}")


def _normalized_update_value(key: str, value: object) -> object:
    if key == "action_type" and value is not None:
        return _common_module.ensure_choice(
            str(value),
            field="action_type",
            allowed=_common_module.ACTION_TYPES,
        )
    if key == "misfire_policy" and value is not None:
        return _common_module.ensure_choice(
            str(value),
            field="misfire_policy",
            allowed=_common_module.MISFIRE_POLICIES,
        )
    return value


def _build_update_sql(changes: dict[str, object], name: str) -> tuple[str, list[object]]:
    assignments: list[str] = []
    values: list[object] = []
    for key, value in changes.items():
        assignments.append(f"{key} = ${len(values) + 1}")
        values.append(_normalized_update_value(key, value))
    assignments.append("updated_at = NOW()")
    values.append(name.strip())
    query = f"UPDATE scheduler_jobs SET {', '.join(assignments)} WHERE name = ${len(values)}"
    return query, values


class JobsStoreMixin:
    async def create_job(
        self: _PoolOwner,
        *,
        name: str,
        job_type: str,
        schedule: str,
        action_type: str,
        action_payload: dict[str, object] | None,
        created_by: str,
        enabled: bool = True,
        auto_delete: bool = False,
        misfire_policy: str = "skip",
        metadata: dict[str, object] | None = None,
        last_run_at: datetime | None = None,
        next_run_at: datetime | None = None,
    ) -> str:
        assert self.pool is not None
        job_type_value = _common_module.ensure_choice(
            job_type,
            field="job_type",
            allowed=_common_module.JOB_TYPES,
        )
        action_type_value = _common_module.ensure_choice(
            action_type,
            field="action_type",
            allowed=_common_module.ACTION_TYPES,
        )
        misfire_policy_value = _common_module.ensure_choice(
            misfire_policy,
            field="misfire_policy",
            allowed=_common_module.MISFIRE_POLICIES,
        )
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                """
                INSERT INTO scheduler_jobs (
                    name, job_type, schedule, action_type, action_payload,
                    enabled, auto_delete, misfire_policy, created_by, metadata,
                    last_run_at, next_run_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
                """,
                name.strip(),
                job_type_value,
                schedule.strip(),
                action_type_value,
                action_payload or {},
                enabled,
                auto_delete,
                misfire_policy_value,
                created_by.strip(),
                metadata or {},
                last_run_at,
                next_run_at,
            )
        if record is None:
            raise _common_module.SchedulerCronError("job insert did not return an id")
        return str(record["id"])

    async def get_job_by_name(
        self: _PoolOwner,
        name: str,
    ) -> dict[str, object] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM scheduler_jobs WHERE name = $1", name.strip()
            )
        return _base_module.row_to_dict(record)

    async def get_job_by_id(
        self: _PoolOwner,
        job_id: str,
    ) -> dict[str, object] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM scheduler_jobs WHERE id = $1", job_id.strip()
            )
        return _base_module.row_to_dict(record)

    async def list_jobs(
        self: _PoolOwner,
        enabled: bool | None = None,
        job_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        filters: list[str] = []
        args: list[object] = []
        assert self.pool is not None
        if enabled is not None:
            args.append(enabled)
            filters.append(f"enabled = ${len(args)}")
        if job_type is not None:
            args.append(
                _common_module.ensure_choice(
                    job_type,
                    field="job_type",
                    allowed=_common_module.JOB_TYPES,
                )
            )
            filters.append(f"job_type = ${len(args)}")
        args.append(_normalize_limit(limit, _common_module.DEFAULT_LIST_LIMIT))
        query = _query_for_list(filters, len(args))

        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, *args)
        jobs: list[dict[str, object]] = []
        for record in records:
            payload = _base_module.row_to_dict(record)
            if payload is not None:
                jobs.append(payload)
        return jobs

    async def update_job(self: _PoolOwner, name: str, **changes: object) -> bool:
        assert self.pool is not None
        _validate_update_keys(changes)
        if not changes:
            return False

        query, values = _build_update_sql(changes, name)
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *values)
        return result.endswith(" 1")  # type: ignore[no-any-return]  # asyncpg returns str

    async def delete_job(self: _PoolOwner, name: str) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM scheduler_jobs WHERE name = $1", name.strip())
        return result.endswith(" 1")  # type: ignore[no-any-return]  # asyncpg returns str
