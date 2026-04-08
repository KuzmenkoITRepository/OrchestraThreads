from __future__ import annotations

from core.scheduler_cron.common import (
    DEFAULT_HISTORY_LIMIT,
    RUN_STATUSES,
    SchedulerCronError,
    ensure_choice,
)
from core.scheduler_cron.store_base import SupportsSchedulerCronPool, rows_to_dicts
from core.scheduler_cron.store_runs_kwargs import CompleteRunValues, parse_complete_run_kwargs

HistoryQuery = tuple[str, list[object]]


def _validated_status(status: str) -> str:
    return ensure_choice(status, field="status", allowed=RUN_STATUSES)


def _history_args(job_id: str, limit: int, status: str | None) -> HistoryQuery:
    args: list[object] = [job_id]
    filters = ["job_id = $1"]
    if status is not None:
        args.append(_validated_status(status))
        filters.append("status = $2")
    args.append(max(1, int(limit or DEFAULT_HISTORY_LIMIT)))
    where_clause = " AND ".join(filters)
    limit_index = len(args)
    query = f"SELECT * FROM scheduler_job_runs WHERE {where_clause} ORDER BY started_at DESC LIMIT ${limit_index}"
    return query, args


def _complete_run_values(
    status: str,
    kwargs: dict[str, object],
) -> tuple[str, CompleteRunValues]:
    status_value = _validated_status(status)
    return status_value, parse_complete_run_kwargs(kwargs)


class RunsStoreMixin:
    async def create_run(
        self: SupportsSchedulerCronPool,
        job_id: str,
        status: str,
    ) -> str:
        assert self.pool is not None
        status_value = _validated_status(status)
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                "INSERT INTO scheduler_job_runs (job_id, status) VALUES ($1, $2) RETURNING id",
                job_id,
                status_value,
            )
        if record is None:
            raise SchedulerCronError("run insert did not return an id")
        return str(record["id"])

    async def complete_run(
        self: SupportsSchedulerCronPool,
        run_id: str,
        status: str,
        **kwargs: object,
    ) -> bool:
        assert self.pool is not None
        status_value, complete_run_values = _complete_run_values(
            status,
            kwargs,
        )
        async with self.pool.acquire() as conn:
            result_text = await conn.execute(
                """
                UPDATE scheduler_job_runs
                SET finished_at = NOW(), status = $2, result = $3, error_message = $4, duration_ms = $5
                WHERE id = $1
                """,
                run_id,
                status_value,
                complete_run_values.result_payload,
                complete_run_values.error_message,
                complete_run_values.duration_ms,
            )
        return str(result_text).endswith(" 1")

    async def get_run_history(
        self: SupportsSchedulerCronPool,
        job_id: str,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        assert self.pool is not None
        history_query, history_args = _history_args(job_id=job_id, limit=limit, status=status)
        async with self.pool.acquire() as conn:
            records = await conn.fetch(history_query, *history_args)
        return rows_to_dicts(records)
