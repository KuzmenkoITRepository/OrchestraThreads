from __future__ import annotations

from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.tests import docker_driver_test_data as data


def manifest_with_passthrough(root: Path) -> AgentManifest:
    manifest = data.create_manifest(root)
    runtime_payload = manifest.runtime.to_dict()
    runtime_payload.pop("driver", None)
    return AgentManifest.from_dict(
        {
            **manifest.to_dict(),
            "runtime": {
                **runtime_payload,
                "env": {data.OPENAI_API_KEY: "manifest-secret", "LOG_LEVEL": "INFO"},
                "env_passthrough": [data.OPENAI_API_KEY],
            },
        },
        manifest_path=manifest.manifest_path,
    )
