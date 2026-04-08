from __future__ import annotations

from core.task_registry.store_base import TaskStoreBase
from core.task_registry.store_checklists import (
    TaskStoreChecklists,
)
from core.task_registry.store_comments import (
    TaskStoreComments,
)
from core.task_registry.store_tasks import TaskStoreTasks


class _TaskStoreContent(
    TaskStoreTasks,
    TaskStoreChecklists,
    TaskStoreComments,
):
    __slots__ = ()


class TaskStore(
    TaskStoreBase,
    _TaskStoreContent,
):
    __slots__ = ()
