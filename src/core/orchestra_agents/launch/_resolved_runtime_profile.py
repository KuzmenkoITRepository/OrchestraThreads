"""Private runtime profile type for launch spec builder."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedRuntimeProfile:
    """Fully merged runtime inputs plus build metadata for later runtimes."""

    image: str
    command: tuple[str, ...]
    entrypoint: str | None
    env: Mapping[str, str]
    env_passthrough: tuple[str, ...]
    build_dockerfile: str | None = None
