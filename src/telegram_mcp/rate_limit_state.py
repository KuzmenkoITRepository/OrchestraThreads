"""Minimal rate-limit resource state for Wave 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class RateLimitState:
    """Tracks FloodWaitError occurrences and rate-limit windows."""

    requests_sent: int = 0
    flood_wait_until: datetime | None = None
    window_start: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def record_request(self) -> None:
        """Record a single outgoing request."""
        self.requests_sent += 1

    def record_flood_wait(self, wait_seconds: int) -> None:
        """Record a FloodWaitError with the given wait duration."""
        now = datetime.now(tz=UTC)
        self.flood_wait_until = now + timedelta(seconds=max(0, wait_seconds))

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the current state."""
        wait_until = self.flood_wait_until.isoformat() if self.flood_wait_until else None
        return {
            "requests_sent": self.requests_sent,
            "flood_wait_until": wait_until,
            "window_start": self.window_start.isoformat(),
        }
