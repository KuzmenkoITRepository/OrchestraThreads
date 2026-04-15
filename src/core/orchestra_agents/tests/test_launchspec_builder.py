from __future__ import annotations

import os
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast
from unittest import TestCase
from unittest import mock as umock

from core.orchestra_agents.errors import ManifestValidationError
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._launchspec_test_assertions import assert_characterized_launch_spec

spec_builder_module = import_module("core.orchestra_agents.launch.spec_builder")
field_resolution_module = import_module("core.orchestra_agents.launch._spec_field_resolution")
manifest_with_passthrough = import_module(
    "core.orchestra_agents.tests._launchspec_test_support",
).manifest_with_passthrough


class _RuntimeProfileLike(Protocol):
    build_dockerfile: str | None


class _LaunchSpecBuilderLike(Protocol):
    def build(self, manifest: Any) -> Any: ...

    def runtime_profile(self, manifest: Any) -> _RuntimeProfileLike: ...


def _builder(
    manifests_root: Path,
    *,
    host_manifests_root: Path | None = None,
    default_network: str | None = None,
    compose_runtime_dir: Path | None = None,
) -> _LaunchSpecBuilderLike:
    return cast(
        _LaunchSpecBuilderLike,
        spec_builder_module.LaunchSpecBuilder(
            manifests_root=manifests_root,
            host_manifests_root=host_manifests_root,
            default_network=default_network,
            compose_runtime_dir=compose_runtime_dir,
        ),
    )


class LaunchSpecParityTests(TestCase):
    def test_build_keeps_characterized_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = data.create_characterization_manifest(root)
            builder = _builder(
                root,
                default_network="agents-net",
                compose_runtime_dir=root / "compose-runtime",
            )

            with umock.patch.dict(os.environ, {data.OPENAI_API_KEY: "secret"}, clear=False):
                spec = builder.build(manifest)

            assert_characterized_launch_spec(spec, manifests_root=root)

    def test_build_preserves_absent_default_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            spec = _builder(root).build(data.create_manifest(root))

            self.assertIsNone(spec.default_network)


class LaunchSpecRuntimeTests(TestCase):
    def test_known_backend_can_omit_runtime_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = data.create_unified_manifest(root, backend_type="agent_mux")
            builder = _builder(root)
            spec = builder.build(manifest)

            self.assertEqual(spec.image, data.MUX_RUNTIME_IMAGE)
            self.assertEqual(
                spec.command, ("python", "-m", "core.orchestra_agents.backends.agent_mux.main")
            )
            self.assertEqual(
                builder.runtime_profile(manifest).build_dockerfile,
                "docker/backends/agent_mux/Dockerfile",
            )

    def test_unknown_backend_requires_runtime_fields(self) -> None:
        raw_payload = {
            "slug": "custom-agent",
            "display_name": "Custom Agent",
            "status": "active",
            "agent": {"working_dir": "/workspace", "http_endpoint": "http://{container_name}:8787"},
            "runtime": {},
            "backend": {"type": "custom_backend", "config": {}},
        }

        with self.assertRaisesRegex(ManifestValidationError, "runtime.image is required"):
            AgentManifest.from_dict(
                raw_payload, manifest_path=Path("/tmp/custom-agent/manifest.yaml")
            )

        manifest = AgentManifest.from_dict(
            {**raw_payload, "runtime": {"image": "custom-runtime:latest"}},
            manifest_path=Path("/tmp/custom-agent/manifest.yaml"),
        )
        with self.assertRaisesRegex(RuntimeError, "missing a runtime command"):
            _builder(Path("/tmp")).build(manifest)

    def test_runtime_profile_merges_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            builder = _builder(root)
            manifest = manifest_with_passthrough(root)

            with umock.patch.dict(os.environ, {data.OPENAI_API_KEY: "secret"}, clear=False):
                spec = builder.build(manifest)

            self.assertIn(("LOG_LEVEL", "INFO"), spec.env)
            self.assertIn((data.OPENAI_API_KEY, "secret"), spec.env)


class LaunchSpecValidationTests(TestCase):
    def test_build_rejects_bad_mount_source_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_manifest = data.create_manifest(root)
            runtime_payload = base_manifest.runtime.to_dict()
            runtime_payload.pop("driver", None)
            manifest = AgentManifest.from_dict(
                {
                    **base_manifest.to_dict(),
                    "runtime": {
                        **runtime_payload,
                        "mounts": [
                            {
                                "type": "bind",
                                "source": "./logs/{missing_value}",
                                "target": "/workspace/logs",
                                "mode": "rw",
                            },
                        ],
                    },
                },
                manifest_path=root / "coding_agent" / "manifest.yaml",
            )

            with self.assertRaisesRegex(RuntimeError, r"runtime\.mounts\[0\]\.source"):
                _builder(root).build(manifest)

    def test_health_resolution_rejects_bad_port(self) -> None:
        manifest = AgentManifest.from_dict(
            {
                "slug": "bad-health-agent",
                "display_name": "Bad Health Agent",
                "status": "active",
                "agent": {
                    "working_dir": "/workspace",
                    "http_endpoint": "http://{container_name}:not-a-port",
                },
                "runtime": {
                    "image": "custom-runtime:latest",
                    "command": ["python", "-m", "app.main"],
                },
                "backend": {"type": "custom_backend", "config": {}},
            },
            manifest_path=Path("/tmp/bad-health-agent/manifest.yaml"),
        )

        with self.assertRaisesRegex(RuntimeError, "invalid agent.http_endpoint port"):
            field_resolution_module.resolve_internal_health_url(
                manifest,
                container_name="orchestra-agent-bad-health-agent",
            )


class LaunchSpecMountTests(TestCase):
    def test_relative_bind_mount_uses_host_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            host_root = Path(tmpdir) / "host-workspace"
            (host_root / "agents" / "secretary").mkdir(parents=True)
            manifest = AgentManifest.from_dict(
                {
                    "slug": "secretary",
                    "display_name": "Secretary",
                    "status": "active",
                    "agent": {
                        "working_dir": "/workspace/agents/secretary",
                        "http_endpoint": "http://{container_name}:8787",
                    },
                    "runtime": {
                        "image": data.SGR_RUNTIME_IMAGE,
                        "command": ["python", "-m", "core.orchestra_agents.backends.sgr.main"],
                        "mounts": [
                            {
                                "type": "bind",
                                "source": "../../",
                                "target": "/workspace",
                                "mode": "rw",
                            }
                        ],
                    },
                    "backend": {
                        "type": "sgr_minimax",
                        "config": {"route_policy": "codex_only", "model": "cx/gpt-5.4-mini"},
                    },
                },
                manifest_path=Path("/container/agents/secretary/manifest.yaml"),
            )
            spec = _builder(
                Path("/container/agents"), host_manifests_root=host_root / "agents"
            ).build(manifest)

            self.assertEqual(
                tuple(
                    (mount.type, mount.source, mount.target, mount.mode) for mount in spec.mounts
                ),
                (
                    ("bind", str(host_root / "agents"), "/orchestra/agents", "ro"),
                    ("bind", str(host_root), "/workspace", "rw"),
                ),
            )
