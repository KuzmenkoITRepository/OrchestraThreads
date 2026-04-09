from __future__ import annotations

from core.orchestra_agents.tests import _docker_driver_test_compose as compose
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

compose_driver = compose.compose_driver
compose_file = compose.compose_file
compose_labels = compose.compose_labels
compose_status_payload = compose.compose_status_payload
missing_build_status = compose.missing_build_status

create_manifest = payloads.create_manifest
create_unified_manifest = payloads.create_unified_manifest
manifest_payload = payloads.manifest_payload
unified_backend_config = payloads.unified_backend_config
unified_manifest_payload = payloads.unified_manifest_payload

BuildCapture = types.BuildCapture
ComposeCapture = types.ComposeCapture
DockerCommand = types.DockerCommand
DockerCommands = types.DockerCommands
