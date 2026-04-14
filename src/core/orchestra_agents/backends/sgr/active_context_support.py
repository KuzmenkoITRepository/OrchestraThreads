from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from core.orchestra_agents import runtime as _rt
from core.orchestra_thread.active_context import clear_active_context, write_active_context

if TYPE_CHECKING:
    from core.orchestra_agents.backends.sgr.backend import SGRMinimaxBackend


@contextmanager
def event_active_context_scope(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    event: Any,
) -> Iterator[None]:
    payload = {
        "context_id": backend.context.current_id,
        "delivery_id": delivery.delivery_id,
        "event_id": event.event_id,
        "event_kind": event.event_kind,
        "thread_id": getattr(event, "thread_id", None),
        "root_thread_id": getattr(event, "root_thread_id", None),
        "parent_thread_id": getattr(event, "parent_thread_id", None),
        "owner_agent_slug": getattr(event, "owner_agent_slug", None),
        "from_agent_slug": getattr(event, "from_agent_slug", None),
        "to_agent_slug": getattr(event, "to_agent_slug", None),
        "source_agent_slug": getattr(event, "from_agent_slug", None),
    }
    write_active_context(payload)
    try:
        yield
    finally:
        clear_active_context()
