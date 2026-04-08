from __future__ import annotations

from core.scheduler_cron import store_jobs_create, store_jobs_list_update, store_jobs_sql
from core.scheduler_cron.common import SchedulerCronError
from core.scheduler_cron.store_base import SupportsSchedulerCronPool, row_to_dict, rows_to_dicts


class JobsStoreMixin:
    async def create_job(self: SupportsSchedulerCronPool, **kwargs: object) -> str:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                store_jobs_sql.INSERT_JOB_SQL,
                *store_jobs_create.create_job_args(kwargs),
            )
        if record is None:
            raise SchedulerCronError("job insert did not return an id")
        return str(record["id"])

    async def get_job_by_name(
        self: SupportsSchedulerCronPool,
        name: str,
    ) -> dict[str, object] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(store_jobs_sql.SELECT_JOB_BY_NAME_SQL, name.strip())
        return row_to_dict(record)

    async def get_job_by_id(
        self: SupportsSchedulerCronPool,
        job_id: str,
    ) -> dict[str, object] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(store_jobs_sql.SELECT_JOB_BY_ID_SQL, job_id.strip())
        return row_to_dict(record)

    async def list_jobs(
        self: SupportsSchedulerCronPool,
        enabled: bool | None = None,
        job_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        assert self.pool is not None
        query, args = store_jobs_list_update.jobs_list_query(
            enabled=enabled,
            job_type=job_type,
            limit=limit,
        )
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, *args)
        return rows_to_dicts(records)

    async def update_job(self: SupportsSchedulerCronPool, name: str, **changes: object) -> bool:
        assert self.pool is not None
        if not changes:
            return False
        query, args = store_jobs_list_update.update_job_statement(name, changes)
        async with self.pool.acquire() as conn:
            response = await conn.execute(query, *args)
        return str(response).endswith(store_jobs_sql.UPDATE_ROW_SQL_SUFFIX)

    async def delete_job(self: SupportsSchedulerCronPool, name: str) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            response = await conn.execute(store_jobs_sql.DELETE_JOB_SQL, name.strip())
        return str(response).endswith(store_jobs_sql.UPDATE_ROW_SQL_SUFFIX)
