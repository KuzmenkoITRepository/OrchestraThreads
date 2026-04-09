from __future__ import annotations

from pathlib import Path
from typing import Any

DockerCommand = list[str]
DockerCommands = list[DockerCommand]
BuildCapture = tuple[dict[str, Any], DockerCommands, Path]
ComposeCapture = tuple[dict[str, Any], DockerCommands, Path]
