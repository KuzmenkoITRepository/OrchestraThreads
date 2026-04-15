from __future__ import annotations

from pathlib import Path

from core.orchestra_agents.tests import _docker_driver_test_constants as const
from core.orchestra_agents.tests import _docker_driver_test_payloads as payloads
from core.orchestra_agents.tests import _docker_driver_test_types as types

AGENT_IMAGE = const.AGENT_IMAGE
CODING_AGENT_CONTAINER = const.CODING_AGENT_CONTAINER
COMPOSE_ENV_KEY = const.COMPOSE_ENV_KEY
COMPOSE_FILE_NAME = const.COMPOSE_FILE_NAME
COMPOSE_PROJECT = const.COMPOSE_PROJECT
DETACHED_FLAG = const.DETACHED_FLAG
DOCKER = const.DOCKER
DRIVER_KEY = const.DRIVER_KEY
EXISTS_KEY = const.EXISTS_KEY
HEALTHY_KEY = const.HEALTHY_KEY
IMAGE_KEY = const.IMAGE_KEY
MUX_RUNTIME_IMAGE = const.MUX_RUNTIME_IMAGE
OPENAI_API_KEY = const.OPENAI_API_KEY
OPENCODE_RUNTIME_IMAGE = const.OPENCODE_RUNTIME_IMAGE
RUN_COMMAND = const.RUN_COMMAND
RUN_PATH = const.RUN_PATH
RUNNING_KEY = const.RUNNING_KEY
SGR_RUNTIME_IMAGE = const.SGR_RUNTIME_IMAGE
STATUS_KEY = const.STATUS_KEY

create_manifest = payloads.create_manifest
create_characterization_manifest = payloads.create_characterization_manifest
create_unified_manifest = payloads.create_unified_manifest
manifest_payload = payloads.manifest_payload
unified_backend_config = payloads.unified_backend_config
unified_manifest_payload = payloads.unified_manifest_payload

BuildCapture = types.BuildCapture
ComposeCapture = types.ComposeCapture
DockerCommand = types.DockerCommand
DockerCommands = types.DockerCommands


def compose_file(root: Path) -> Path:
    return root / "compose-runtime" / COMPOSE_FILE_NAME


def compose_labels() -> dict[str, str]:
    return {
        "com.docker.compose.project": COMPOSE_PROJECT,
        "com.docker.compose.service": "agent-coding-agent",
    }


def compose_status_payload() -> dict[str, bool]:
    return {
        EXISTS_KEY: True,
        RUNNING_KEY: True,
        HEALTHY_KEY: True,
    }


def missing_build_status() -> dict[str, bool]:
    return {
        EXISTS_KEY: True,
        RUNNING_KEY: True,
        HEALTHY_KEY: False,
    }
