from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TaskCreateRequest:
    title: str
    description: str | None
    created_by: str
    status: str = "draft"
    assignee: str | None = None
    priority: str = "normal"
    acceptance_criteria: str | None = None
    linked_thread_id: UUID | str | None = None
    blocked_by: list[UUID | str] | None = None
    artifacts: list[dict[str, Any]] | None = None
