from __future__ import annotations

from importlib import import_module
from typing import Any, cast

_store_base_module = import_module("core.scheduler_cron.store_base")
_store_jobs_module = import_module("core.scheduler_cron.store_jobs")
_store_runs_module = import_module("core.scheduler_cron.store_runs")

SchedulerCronStoreBase = cast(Any, _store_base_module.SchedulerCronStoreBase)
JobsStoreMixin = cast(Any, _store_jobs_module.JobsStoreMixin)
RunsStoreMixin = cast(Any, _store_runs_module.RunsStoreMixin)


class SchedulerCronStore(SchedulerCronStoreBase, JobsStoreMixin, RunsStoreMixin):  # type: ignore[valid-type,misc]  # dynamic mixin composition
    __slots__ = ()
