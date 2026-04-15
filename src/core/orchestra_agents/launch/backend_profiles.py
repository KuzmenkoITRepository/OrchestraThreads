"""Known backend launch profiles for pure launch spec building."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class BackendProfile:
    """Platform-managed runtime defaults and build metadata for a backend."""

    image: str
    command: tuple[str, ...]
    build_dockerfile: str | None = None
    entrypoint: str | None = None
    env: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    env_passthrough: tuple[str, ...] = ()


def _mapping_proxy(values: dict[str, str]) -> Mapping[str, str]:
    return MappingProxyType(values)


KNOWN_BACKEND_PROFILES = MappingProxyType(
    {
        "example": BackendProfile(
            image="orchestra-agent-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.example.main"),
            build_dockerfile="docker/backends/sgr/Dockerfile",
        ),
        "sgr_minimax": BackendProfile(
            image="orchestra-sgr-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.sgr.main"),
            build_dockerfile="docker/backends/sgr/Dockerfile",
            env=_mapping_proxy({"PYTHONPATH": "/workspace/src:/workspace"}),
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
        "agent_mux": BackendProfile(
            image="orchestra-agent-mux-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.agent_mux.main"),
            build_dockerfile="docker/backends/agent_mux/Dockerfile",
            env=_mapping_proxy(
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
        "opencode_omo": BackendProfile(
            image="orchestra-opencode-runtime:latest",
            command=("python", "-m", "core.orchestra_agents.backends.opencode.main"),
            build_dockerfile="docker/backends/opencode/Dockerfile",
            env=_mapping_proxy(
                {
                    "PYTHONPATH": "/workspace/src",
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
        **{
            profile.image: profile.build_dockerfile
            for profile in KNOWN_BACKEND_PROFILES.values()
            if profile.build_dockerfile is not None
        },
    }
)


def backend_profile(backend_type: str) -> BackendProfile | None:
    """Return profile for a known backend type."""

    return KNOWN_BACKEND_PROFILES.get(str(backend_type).strip())


def local_runtime_dockerfile(image: str) -> str | None:
    """Return Dockerfile path used to build a known local image."""

    return LOCAL_RUNTIME_IMAGE_DOCKERFILES.get(str(image).strip())


def merge_env_passthrough(
    defaults: Sequence[str],
    overrides: Sequence[str],
) -> tuple[str, ...]:
    """Merge passthrough keys while preserving first-seen order."""

    merged = list(defaults)
    for key in overrides:
        if key not in merged:
            merged.append(key)
    return tuple(merged)
