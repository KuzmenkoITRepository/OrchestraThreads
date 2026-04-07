from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, cast


class _CommonModule(Protocol):
    DEFAULT_HISTORY_LIMIT: int
    RUN_STATUSES: tuple[str, ...]
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


def _history_query(filters: list[str], args_length: int) -> str:
    return (
        "SELECT * FROM scheduler_job_runs WHERE "
        + " AND ".join(filters)
        + f" ORDER BY started_at DESC LIMIT ${args_length}"
    )


class RunsStoreMixin:
    async def create_run(self: _PoolOwner, job_id: str, status: str) -> str:
        assert self.pool is not None
        status_value = _common_module.ensure_choice(
            status,
            field="status",
            allowed=_common_module.RUN_STATUSES,
        )
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                "INSERT INTO scheduler_job_runs (job_id, status) VALUES ($1, $2) RETURNING id",
                job_id,
                status_value,
            )
        if record is None:
            raise _common_module.SchedulerCronError("run insert did not return an id")
        return str(record["id"])

    async def complete_run(
        self: _PoolOwner,
        run_id: str,
        status: str,
        *,
        result: dict[str, object] | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> bool:
        assert self.pool is not None
        status_value = _common_module.ensure_choice(
            status,
            field="status",
            allowed=_common_module.RUN_STATUSES,
        )
        async with self.pool.acquire() as conn:
            result_value = await conn.execute(
                """
                UPDATE scheduler_job_runs
                SET finished_at = NOW(), status = $2, result = $3, error_message = $4, duration_ms = $5
                WHERE id = $1
                """,
                run_id,
                status_value,
                result,
                error_message,
                duration_ms,
            )
        return result_value.endswith(" 1")  # type: ignore[no-any-return]  # asyncpg returns str

    async def get_run_history(
        self: _PoolOwner,
        job_id: str,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        filters = ["job_id = $1"]
        args: list[object] = [job_id]
        assert self.pool is not None
        if status is not None:
            args.append(
                _common_module.ensure_choice(
                    status,
                    field="status",
                    allowed=_common_module.RUN_STATUSES,
                )
            )
            filters.append(f"status = ${len(args)}")
        args.append(_normalize_limit(limit, _common_module.DEFAULT_HISTORY_LIMIT))
        query = _history_query(filters, len(args))
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, *args)
        history: list[dict[str, object]] = []
        for record in records:
            payload = _base_module.row_to_dict(record)
            if payload is not None:
                history.append(payload)
        return history
