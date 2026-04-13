"""Known backend runtime specifications for Docker-managed agents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class BackendRuntimeSpec:
    """Platform-managed runtime defaults for a known backend."""

    image: str
    command: tuple[str, ...]
    dockerfile: str
    entrypoint: str | None = None
    env: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    env_passthrough: tuple[str, ...] = ()


BACKEND_RUNTIME_SPECS = MappingProxyType(
    {
        "sgr_minimax": BackendRuntimeSpec(
            image="orchestra-sgr-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.sgr.main"),
            dockerfile="docker/backends/sgr/Dockerfile",
            env=MappingProxyType({"PYTHONPATH": "/app/src"}),
            env_passthrough=(
                "OMNIROUTE_URL",
                "OMNIROUTE_API_KEY",
                "LLM_CLIENT_MODEL",
                "LLM_CLIENT_ROUTE_POLICY",
                "LLM_CLIENT_TIMEOUT_SECONDS",
                "LLM_CLIENT_TEMPERATURE",
                "LLM_CLIENT_MAX_TOKENS",
                "LLM_CLIENT_REASONING_EFFORT",
                "LLM_CLIENT_REASONING_SUMMARY",
                "SGR_MAX_REASONING_STEPS",
                "SGR_MAX_DIRECT_TEXT_RETRIES",
                "LOG_LEVEL",
            ),
        ),
        "agent_mux": BackendRuntimeSpec(
            image="orchestra-agent-mux-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.agent_mux.main"),
            dockerfile="docker/backends/agent_mux/Dockerfile",
            env=MappingProxyType(
                {
                    "PYTHONPATH": "/workspace/src",
                    "ORCHESTRA_THREADS_URL": "http://orchestra-threads:8788",
                    "AGENT_MUX_BINARY": "agent-mux",
                }
            ),
            env_passthrough=(
                "ORCHESTRA_THREADS_URL",
                "OMNIROUTE_URL",
                "OMNIROUTE_API_KEY",
                "AGENT_MUX_BINARY",
                "LOG_LEVEL",
            ),
        ),
        "opencode_omo": BackendRuntimeSpec(
            image="orchestra-opencode-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.opencode.main"),
            dockerfile="docker/backends/opencode/Dockerfile",
            env=MappingProxyType(
                {
                    "PYTHONPATH": "/app/src",
                    "ORCHESTRA_THREADS_URL": "http://orchestra-threads:8788",
                    "OPENCODE_RUNTIME_STATE_ROOT": "/tmp/opencode-runtime/{slug}",
                }
            ),
            env_passthrough=(
                "ORCHESTRA_THREADS_URL",
                "OMNIROUTE_URL",
                "OMNIROUTE_API_KEY",
                "OPENCODE_RUNTIME_STATE_ROOT",
                "LOG_LEVEL",
            ),
        ),
    }
)

LOCAL_RUNTIME_IMAGE_DOCKERFILES = MappingProxyType(
    {
        **{spec.image: spec.dockerfile for spec in BACKEND_RUNTIME_SPECS.values()},
        "orchestra-agent-runtime:latest": "docker/backends/sgr/Dockerfile",
    }
)


def local_runtime_dockerfile(image: str) -> str | None:
    """Return the Dockerfile used to build a known local runtime image."""

    return LOCAL_RUNTIME_IMAGE_DOCKERFILES.get(str(image).strip())
