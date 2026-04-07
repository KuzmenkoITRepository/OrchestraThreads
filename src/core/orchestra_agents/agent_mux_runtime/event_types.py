"""Normalized event types for event-centric session routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedEvent:
    """
    Normalized internal event representation.

    External events are converted to this stable schema before routing.
    The runtime core operates only on NormalizedEvent instances.
    """

    event_id: str
    source: str
    routing_key: str
    kind: str
    payload: dict[str, Any]
    created_at: str
    interrupt: bool = False
    priority: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate required fields."""
        _require_non_empty(
            event_id=self.event_id,
            source=self.source,
            routing_key=self.routing_key,
            kind=self.kind,
            created_at=self.created_at,
        )


def _require_non_empty(**fields: str) -> None:
    for name, value in fields.items():
        if not value:
            raise ValueError(f"{name} is required")
