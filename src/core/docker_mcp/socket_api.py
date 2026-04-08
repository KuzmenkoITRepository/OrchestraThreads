from __future__ import annotations

import subprocess
from urllib.parse import quote

_DOCKER_TIMEOUT_SECONDS = 30
_DOCKER_SOCKET = "/var/run/docker.sock"
_DOCKER_API_URL = "http://localhost"


def docker_api_get(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            "curl",
            "--silent",
            "--show-error",
            "--unix-socket",
            _DOCKER_SOCKET,
            f"{_DOCKER_API_URL}{path}",
        ],
        capture_output=True,
        text=True,
        timeout=_DOCKER_TIMEOUT_SECONDS,
        check=False,
    )


def docker_api_get_bytes(path: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603
        [
            "curl",
            "--silent",
            "--show-error",
            "--unix-socket",
            _DOCKER_SOCKET,
            f"{_DOCKER_API_URL}{path}",
        ],
        capture_output=True,
        text=False,
        timeout=_DOCKER_TIMEOUT_SECONDS,
        check=False,
    )


def container_path(container_name: str) -> str:
    return quote(container_name, safe="")


def logs_path(container_name: str, *, tail: int, since: object) -> str:
    parts = ["stdout=1", "stderr=1", f"tail={tail}"]
    since_text = str(since or "").strip()
    if since_text:
        parts.append(f"since={quote(since_text, safe='')}")
    query = "&".join(parts)
    return f"/containers/{container_path(container_name)}/logs?{query}"
