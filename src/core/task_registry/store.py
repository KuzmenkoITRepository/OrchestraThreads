from __future__ import annotations

from core.task_registry.store_base import TaskStoreBase
from core.task_registry.store_checklists import (
    TaskStoreChecklists,
)
from core.task_registry.store_comments import (
    TaskStoreComments,
)
from core.task_registry.store_tasks import TaskStoreTasks


class TaskStore(  # noqa: WPS215  # The facade intentionally composes multiple mixins.
    TaskStoreBase,
    TaskStoreTasks,
    TaskStoreChecklists,
    TaskStoreComments,
):
    __slots__ = ()
