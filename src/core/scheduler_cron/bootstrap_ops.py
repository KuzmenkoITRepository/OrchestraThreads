from __future__ import annotations

import asyncio
from typing import Protocol, cast

from core.scheduler_cron.bootstrap_data import job_definitions


class _EngineProtocol(Protocol):
    async def add_job(self, job: dict[str, object]) -> None: ...


class _StoreProtocol(Protocol):
    async def get_job_by_name(self, name: str) -> dict[str, object] | None: ...

    async def create_job(self, **kwargs: object) -> str: ...

    async def get_job_by_id(self, job_id: str) -> dict[str, object] | None: ...

    async def update_job(self, name: str, **changes: object) -> bool: ...


def _job_payload(job_def: dict[str, object]) -> dict[str, object]:
    return {
        "schedule": str(job_def["schedule"]),
        "action_type": str(job_def["action_type"]),
        "action_payload": cast(dict[str, object], job_def["action_payload"]),
        "enabled": bool(job_def["enabled"]),
        "auto_delete": bool(job_def["auto_delete"]),
        "misfire_policy": str(job_def["misfire_policy"]),
    }


def _create_payload(job_def: dict[str, object]) -> dict[str, object]:
    payload = _job_payload(job_def)
    payload.update(
        {
            "name": str(job_def["name"]),
            "job_type": str(job_def["job_type"]),
            "created_by": str(job_def["created_by"]),
        }
    )
    return payload


async def _refresh_existing(
    store: _StoreProtocol,
    engine: _EngineProtocol,
    name: str,
    payload: dict[str, object],
) -> None:
    await store.update_job(name, **payload)
    refreshed = await store.get_job_by_name(name)
    if refreshed is not None and bool(refreshed.get("enabled")):
        await engine.add_job(refreshed)


async def _apply_job(
    store: _StoreProtocol,
    engine: _EngineProtocol,
    job_def: dict[str, object],
) -> str | None:
    name = str(job_def["name"])
    existing = await store.get_job_by_name(name)
    if existing is not None:
        await _refresh_existing(store, engine, name, _job_payload(job_def))
        return None
    create_payload = _create_payload(job_def)
    job_id = await store.create_job(**create_payload)
    job = await store.get_job_by_id(job_id)
    if job is not None and bool(job.get("enabled")):
        await engine.add_job(job)
        return str(create_payload["name"])
    return None


async def bootstrap_jobs(store: _StoreProtocol, engine: _EngineProtocol) -> list[str]:
    created_names = await asyncio.gather(
        *(_apply_job(store, engine, cast(dict[str, object], raw)) for raw in job_definitions())
    )
    return [name for name in created_names if name is not None]
