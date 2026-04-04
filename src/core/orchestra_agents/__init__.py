"""Manifest-driven Docker lifecycle service for Orchestra agents."""

from .docker_driver import DockerDriver
from .manifest import AgentManifest, ManifestValidationError
from .registry import AgentManifestRegistry
from .service import OrchestraAgentsService, build_app

__all__ = [
    "AgentManifest",
    "AgentManifestRegistry",
    "DockerDriver",
    "ManifestValidationError",
    "OrchestraAgentsService",
    "build_app",
]
