from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from core.orchestra_agents.launch.launch_spec import LaunchSpec
from core.orchestra_agents.launch.spec_builder import LaunchSpecBuilder
from core.orchestra_agents.tests import docker_driver_test_data as data


def driver_support_dirname() -> str:
    support = import_module("core.orchestra_agents._docker_driver_support")
    return str(support.COMPOSE_RUNTIME_DIRNAME)


def build_characterized_spec(
    manifests_root: Path,
    *,
    default_network: str | None = None,
) -> LaunchSpec:
    return LaunchSpecBuilder(
        manifests_root=manifests_root,
        default_network=default_network,
        compose_runtime_dir=manifests_root / driver_support_dirname(),
    ).build(data.create_characterization_manifest(manifests_root))


def build_spec(
    manifests_root: Path,
    *,
    manifest_factory: str = "create_manifest",
    factory_kwargs: dict[str, Any] | None = None,
) -> LaunchSpec:
    kwargs = {} if factory_kwargs is None else dict(factory_kwargs)
    manifest = getattr(data, manifest_factory)(manifests_root, **kwargs)
    return LaunchSpecBuilder(
        manifests_root=manifests_root,
        default_network=None,
        compose_runtime_dir=manifests_root / driver_support_dirname(),
    ).build(manifest)


def build_unified_spec(manifests_root: Path, *, backend_type: str) -> LaunchSpec:
    return LaunchSpecBuilder(manifests_root=manifests_root).build(
        data.create_unified_manifest(manifests_root, backend_type=backend_type),
    )
