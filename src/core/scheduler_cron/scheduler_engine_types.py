from __future__ import annotations

from typing import Any, Protocol, TypedDict, Unpack


class CompleteRunChanges(TypedDict, total=False):
    result: dict[str, object] | None
    error_message: str | None
    duration_ms: int | None


class JobRunner(Protocol):
    async def __call__(
        self,
        job_id: str,
        action_type: str,
        action_payload: dict[str, object],
        auto_delete: bool,
    ) -> None: ...


class RemoveJobCallback(Protocol):
    async def __call__(self, job_id: str) -> bool: ...


class ExecutorCallbackProtocol(Protocol):
    async def __call__(
        self,
        action_type: str,
        action_payload: dict[str, object],
    ) -> dict[str, object]: ...


class SchedulerStoreProtocol(Protocol):
    async def list_jobs(
        self,
        enabled: bool | None = None,
    ) -> list[dict[str, object]]: ...

    async def create_run(self, job_id: str, status: str) -> str: ...

    async def complete_run(
        self,
        run_id: str,
        status: str,
        **changes: Unpack[CompleteRunChanges],
    ) -> bool: ...

    async def get_job_by_id(self, job_id: str) -> dict[str, object] | None: ...

    async def update_job(self, name: str, **changes: object) -> bool: ...

    async def delete_job(self, name: str) -> bool: ...


class SchedulerProtocol(Protocol):
    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...

    def get_jobs(self) -> list[Any]: ...

    def add_job(self, **kwargs: object) -> object: ...

    def remove_job(self, job_id: str) -> None: ...

    def pause_job(self, job_id: str) -> None: ...

    def resume_job(self, job_id: str) -> None: ...
