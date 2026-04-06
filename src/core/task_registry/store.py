from __future__ import annotations

from core.task_registry.store_base import TaskStoreBase  # type: ignore[reportMissingImports]
from core.task_registry.store_checklists import (  # type: ignore[reportMissingImports]
    TaskStoreChecklists,
)
from core.task_registry.store_comments import (  # type: ignore[reportMissingImports]
    TaskStoreComments,
)
from core.task_registry.store_tasks import TaskStoreTasks  # type: ignore[reportMissingImports]


class TaskStore(  # noqa: WPS215  # The facade intentionally composes multiple mixins.
    TaskStoreBase,
    TaskStoreTasks,
    TaskStoreChecklists,
    TaskStoreComments,
):
    __slots__ = ()
