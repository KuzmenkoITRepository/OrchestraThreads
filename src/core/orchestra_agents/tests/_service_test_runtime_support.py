from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.orchestra_agents.tests._service_test_fakes import FakeLaunchSpec, FakeServiceState


def compute_is_running(
    *,
    spec: FakeLaunchSpec,
    started: list[str],
    restarted: list[str],
    running: bool | None,
) -> bool:
    if running is not None:
        return running
    return spec.slug in started or spec.slug in restarted


def public_field_names(state_type: type[FakeServiceState]) -> set[str]:
    return {item.name for item in fields(state_type) if not item.name.startswith("_")}
