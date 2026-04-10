"""Docker-backed runtime driver for manifest-defined agents."""

from __future__ import annotations

import json
import os
import subprocess
import typing as t
from pathlib import Path

from core.orchestra_agents import _docker_driver_support as driver_support
from core.orchestra_agents import _docker_runtime_resolution as runtime_resolution
from core.orchestra_agents import manifest as manifest_module


def _run(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _endpoint_port(endpoint: str) -> int | None:
    without_scheme = endpoint.split("://", maxsplit=1)[-1]
    host_and_path = without_scheme.split("/", maxsplit=1)[0]
    if ":" not in host_and_path:
        return None
    raw_port = host_and_path.rsplit(":", maxsplit=1)[-1].strip()
    if not raw_port.isdigit():
        return None
    return int(raw_port)


def resolve_backend_runtime(
    manifest: manifest_module.AgentManifest,
) -> runtime_resolution.ResolvedRuntimeConfig:
    return runtime_resolution.resolve_backend_runtime(manifest)


class DockerDriver:  # noqa: WPS214, WPS230 - Docker lifecycle driver is intentionally a single stateful orchestration boundary.
    """Start, stop, and inspect agent containers through Docker."""

    def __init__(
        self,
        *,
        manifests_root: str | Path,
        **options: t.Unpack[driver_support.InitOptions],
    ) -> None:
        self.manifests_root = Path(manifests_root).expanduser().resolve()
        self.container_name_prefix = str(
            options.get("container_name_prefix")
            or os.getenv("ORCHESTRA_AGENTS_CONTAINER_NAME_PREFIX")
            or "orchestra-agent-"
        )
        self.default_network = (
            str(
                options.get("default_network") or os.getenv("ORCHESTRA_AGENTS_DOCKER_NETWORK") or ""
            ).strip()
            or None
        )
        self.manifest_mount_path = str(
            options.get("manifest_mount_path")
            or os.getenv("ORCHESTRA_AGENTS_MANIFEST_MOUNT_PATH")
            or "/orchestra/agents"
        ).rstrip("/")
        timeout_source: float | str
        timeout_option = options.get("health_timeout_seconds")
        if timeout_option is None:
            timeout_source = os.getenv("ORCHESTRA_AGENTS_HEALTH_TIMEOUT_SECONDS", "2")
        else:
            timeout_source = str(timeout_option)
        self.health_timeout_seconds = max(
            0.2,
            float(timeout_source),
        )
        auto_build_value = options.get("auto_build_local_images")
        if auto_build_value is None:
            normalized = (
                str(os.getenv("ORCHESTRA_AGENTS_AUTO_BUILD_LOCAL_IMAGES", "true")).strip().lower()
            )
            auto_build_value = normalized not in {"0", "false", "no", "off"}
        self.auto_build_local_images = bool(auto_build_value)
        self._build_context_root = (
            Path(
                options.get("build_context_root")
                or os.getenv("ORCHESTRA_AGENTS_IMAGE_BUILD_CONTEXT")
                or self.manifests_root.parent
            )
            .expanduser()
            .resolve()
        )
        self.compose_project_name = self._resolve_compose_project_name(options)
        self._compose_runtime_dir = self._resolve_compose_runtime_dir(options)

    def container_name(self, slug: str) -> str:
        return f"{self.container_name_prefix}{str(slug).strip()}"

    def start(self, manifest: manifest_module.AgentManifest) -> dict[str, t.Any]:
        self._ensure_startable(manifest)
        container_name = self.container_name(manifest.slug)
        if self._compose_enabled():
            return self._start_with_compose(manifest, container_name=container_name)
        if self._container_exists(container_name):
            return self._start_existing(manifest, container_name=container_name)
        return self._start_new(manifest, container_name=container_name)

    def stop(self, slug: str, *, remove: bool = False) -> dict[str, t.Any]:
        container_name = self.container_name(slug)
        if self._compose_enabled():
            return self._stop_compose_service(slug, container_name=container_name, remove=remove)
        if not self._container_exists(container_name):
            return self._stop_result(slug, container_name=container_name, removed=False)
        self._run_checked(
            ["docker", "stop", container_name],
            timeout=120,
            error_message=f"failed to stop {container_name}",
        )
        removed = False
        if remove:
            self._run_checked(
                ["docker", "rm", "-f", container_name],
                timeout=120,
                error_message=f"failed to remove {container_name}",
            )
            removed = True
        return self._stop_result(slug, container_name=container_name, removed=removed)

    def restart(self, manifest: manifest_module.AgentManifest) -> dict[str, t.Any]:
        self._ensure_startable(manifest)
        container_name = self.container_name(manifest.slug)
        if self._compose_enabled():
            return self._restart_with_compose(manifest, container_name=container_name)
        if not self._container_exists(container_name):
            return self.start(manifest)
        self.stop(manifest.slug, remove=True)
        status = self._start_new(manifest, container_name=container_name)
        status["message"] = "container recreated"
        return status

    def status(self, manifest_or_slug: manifest_module.AgentManifest | str) -> dict[str, t.Any]:
        context = self._status_context(manifest_or_slug)
        inspect_result = _run(
            ["docker", "inspect", context.container_name, "--format", "{{json .State}}"],
            timeout=30,
        )
        if inspect_result.returncode != 0:
            return self._missing_status(context, inspect_result.stderr)
        state = json.loads(inspect_result.stdout.strip() or "{}")
        return self._running_status(context, state)

    def _status_context(
        self,
        manifest_or_slug: manifest_module.AgentManifest | str,
    ) -> driver_support.StatusContext:
        if isinstance(manifest_or_slug, manifest_module.AgentManifest):
            slug = manifest_or_slug.slug
            container_name = self.container_name(slug)
            return driver_support.StatusContext(
                slug=slug,
                backend_type=manifest_or_slug.backend.type,
                endpoint=manifest_or_slug.resolve_http_endpoint(container_name=container_name),
                container_name=container_name,
            )
        slug = str(manifest_or_slug).strip()
        return driver_support.StatusContext(
            slug=slug, backend_type=None, endpoint=None, container_name=self.container_name(slug)
        )

    def _missing_status(
        self,
        context: driver_support.StatusContext,
        stderr: str,
    ) -> dict[str, t.Any]:
        return {
            "slug": context.slug,
            "container_name": context.container_name,
            "exists": False,
            "running": False,
            "healthy": False,
            "backend_type": context.backend_type,
            "http_endpoint": context.endpoint,
            "docker_status": None,
            "health_status": None,
            "started_at": None,
            "last_error": stderr.strip() or None,
        }

    def _running_status(
        self,
        context: driver_support.StatusContext,
        state: dict[str, t.Any],
    ) -> dict[str, t.Any]:
        health_status, healthy, last_error, running = self._resolve_health(
            state, endpoint=context.endpoint
        )
        return {
            "slug": context.slug,
            "container_name": context.container_name,
            "exists": True,
            "running": running,
            "healthy": healthy,
            "backend_type": context.backend_type,
            "http_endpoint": context.endpoint,
            "docker_status": str(state.get("Status") or "").strip() or None,
            "health_status": health_status,
            "started_at": state.get("StartedAt"),
            "last_error": last_error,
        }

    def _resolve_health(
        self,
        state: dict[str, t.Any],
        *,
        endpoint: str | None,
    ) -> driver_support.HealthResult:
        running = bool(state.get("Running"))
        last_error = str(state.get("Error") or "").strip() or None
        docker_health_status = self._docker_health_status(state)
        if running and docker_health_status == "healthy":
            return self._healthy_docker_status(last_error, docker_health_status)
        if running and docker_health_status:
            return self._unhealthy_docker_status(last_error, docker_health_status)
        if running and endpoint:
            return self._http_health_status(endpoint, last_error)
        return None, False, last_error, running

    def _docker_health_status(self, state: dict[str, t.Any]) -> str:
        health_state = state.get("Health")
        if isinstance(health_state, dict):
            return str(health_state.get("Status") or "").strip().lower()
        return ""

    def _healthy_docker_status(
        self,
        last_error: str | None,
        docker_health_status: str,
    ) -> driver_support.HealthResult:
        return (
            {
                "ok": True,
                "status_code": 200,
                "source": "docker",
                "status": docker_health_status,
            },
            True,
            last_error,
            True,
        )

    def _unhealthy_docker_status(
        self,
        last_error: str | None,
        docker_health_status: str,
    ) -> driver_support.HealthResult:
        return (
            {
                "ok": False,
                "status_code": None,
                "source": "docker",
                "status": docker_health_status,
            },
            False,
            last_error or docker_health_status,
            True,
        )

    def _http_health_status(
        self,
        endpoint: str,
        last_error: str | None,
    ) -> driver_support.HealthResult:
        health_status = self._probe_health(endpoint)
        healthy = bool(health_status.get("ok"))
        if not healthy and last_error is None:
            last_error = str(health_status.get("error") or "").strip() or None
        return health_status, healthy, last_error, True

    def _build_run_command(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> list[str]:
        resolved_runtime = runtime_resolution.resolve_backend_runtime(manifest)
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--restart",
            "no",
            "--label",
            f"orchestra.agent_slug={manifest.slug}",
            "--label",
            f"orchestra.backend_type={manifest.backend.type}",
            "--workdir",
            manifest.agent.working_dir,
            "-e",
            f"ORCHESTRA_AGENT_SLUG={manifest.slug}",
            "-e",
            f"ORCHESTRA_AGENT_BACKEND_TYPE={manifest.backend.type}",
            "-e",
            f"ORCHESTRA_AGENT_HTTP_ENDPOINT={manifest.resolve_http_endpoint(container_name=container_name)}",
            "-e",
            f"ORCHESTRA_AGENT_WORKING_DIR={manifest.agent.working_dir}",
            "-e",
            "ORCHESTRA_AGENT_ALLOWED_PEER_AGENT_SLUGS="
            + ",".join(manifest.agent.allowed_peer_agent_slugs),
            "-e",
            f"ORCHESTRA_AGENT_MANIFESTS_DIR={self.manifest_mount_path}",
            "--health-cmd",
            self._healthcheck_command(manifest, container_name=container_name),
            "--health-interval",
            "30s",
            "--health-timeout",
            "5s",
            "--health-start-period",
            "10s",
            "--health-retries",
            "3",
            "-v",
            f"{self.manifests_root}:{self.manifest_mount_path}:ro",
        ]
        if self.default_network:
            command.extend(["--network", self.default_network])

        command.extend(
            ["-e", f"ORCHESTRA_AGENT_MANIFEST={self._container_manifest_path(manifest)}"]
        )
        if manifest.agent.system_prompt_file:
            command.extend(
                ["-e", f"ORCHESTRA_AGENT_SYSTEM_PROMPT_FILE={manifest.agent.system_prompt_file}"]
            )

        for key, value in self._render_env(
            manifest,
            resolved_runtime,
            container_name=container_name,
        ).items():
            command.extend(["-e", f"{key}={value}"])

        for mount in resolved_runtime.mounts:
            command.extend(
                ["-v", self._render_mount_spec(manifest, mount, container_name=container_name)]
            )

        if resolved_runtime.entrypoint:
            command.extend(["--entrypoint", resolved_runtime.entrypoint])

        command.append(resolved_runtime.image)
        command.extend(resolved_runtime.command)
        return command

    def _resolve_compose_project_name(
        self,
        options: driver_support.InitOptions,
    ) -> str | None:
        project_name = str(
            options.get("compose_project_name")
            or os.getenv("ORCHESTRA_AGENTS_COMPOSE_PROJECT_NAME")
            or ""
        ).strip()
        return project_name or None

    def _resolve_compose_runtime_dir(
        self,
        options: driver_support.InitOptions,
    ) -> Path:
        runtime_dir = Path(
            options.get("compose_runtime_dir")
            or os.getenv("ORCHESTRA_AGENTS_COMPOSE_RUNTIME_DIR")
            or self.manifests_root.parent / driver_support.COMPOSE_RUNTIME_DIRNAME
        )
        return runtime_dir.expanduser().resolve()

    def _compose_enabled(self) -> bool:
        return self.compose_project_name is not None

    def _compose_service_name(self, slug: str) -> str:
        normalized_slug = str(slug).strip().replace("_", "-")
        return f"{driver_support.COMPOSE_SERVICE_PREFIX}{normalized_slug}"

    def _compose_file_path(self, slug: str) -> Path:
        return self._compose_runtime_dir / f"{slug}.yaml"

    def _compose_command(self, compose_file: Path, *args: str) -> list[str]:
        assert self.compose_project_name is not None
        return [
            "docker",
            "compose",
            "-p",
            self.compose_project_name,
            "-f",
            str(compose_file),
            *args,
        ]

    def _start_with_compose(
        self, manifest: manifest_module.AgentManifest, *, container_name: str
    ) -> dict[str, t.Any]:
        resolved_runtime = runtime_resolution.resolve_backend_runtime(manifest)
        self._ensure_image_available(resolved_runtime.image)
        compose_file = self._write_compose_file(manifest, container_name=container_name)
        self._remove_legacy_container_if_needed(manifest, container_name=container_name)
        self._run_checked(
            self._compose_command(
                compose_file,
                "up",
                "-d",
                "--no-deps",
                self._compose_service_name(manifest.slug),
            ),
            timeout=300,
            error_message=f"failed to start {manifest.slug}",
        )
        status = self.status(manifest)
        status["message"] = "compose service ensured"
        return status

    def _restart_with_compose(
        self, manifest: manifest_module.AgentManifest, *, container_name: str
    ) -> dict[str, t.Any]:
        resolved_runtime = runtime_resolution.resolve_backend_runtime(manifest)
        self._ensure_image_available(resolved_runtime.image)
        compose_file = self._write_compose_file(manifest, container_name=container_name)
        self._remove_legacy_container_if_needed(manifest, container_name=container_name)
        self._run_checked(
            self._compose_command(
                compose_file,
                "up",
                "-d",
                "--force-recreate",
                "--no-deps",
                self._compose_service_name(manifest.slug),
            ),
            timeout=300,
            error_message=f"failed to restart {manifest.slug}",
        )
        status = self.status(manifest)
        status["message"] = "compose service recreated"
        return status

    def _stop_compose_service(
        self,
        slug: str,
        *,
        container_name: str,
        remove: bool,
    ) -> dict[str, t.Any]:
        compose_file = self._compose_file_path(slug)
        container_exists = self._container_exists(container_name)
        self._ensure_compose_metadata(
            slug, compose_file, container_exists=container_exists, remove=remove
        )
        if not container_exists:
            return self._stop_result(slug, container_name=container_name, removed=False)
        self._run_checked(
            self._compose_stop_command(slug, compose_file, remove=remove),
            timeout=120,
            error_message=f"failed to stop {container_name}",
        )
        self._cleanup_compose_file(compose_file, remove=remove)
        return self._stop_result(slug, container_name=container_name, removed=remove)

    def _ensure_compose_metadata(
        self,
        slug: str,
        compose_file: Path,
        *,
        container_exists: bool,
        remove: bool,
    ) -> None:
        if compose_file.exists():
            return
        if remove and not container_exists:
            return
        raise RuntimeError(
            f"compose metadata missing for compose-managed agent {slug}: {compose_file}"
        )

    def _compose_stop_command(self, slug: str, compose_file: Path, *, remove: bool) -> list[str]:
        service_name = self._compose_service_name(slug)
        command = ["rm", "-sf", service_name] if remove else ["stop", service_name]
        return self._compose_command(compose_file, *command)

    def _cleanup_compose_file(self, compose_file: Path, *, remove: bool) -> None:
        if remove and compose_file.exists():
            compose_file.unlink()

    def _stop_result(self, slug: str, *, container_name: str, removed: bool) -> dict[str, t.Any]:
        return {
            "slug": slug,
            "container_name": container_name,
            "exists": not removed,
            "running": False,
            "removed": removed,
        }

    def _stop_with_docker(
        self,
        slug: str,
        *,
        container_name: str,
        remove: bool,
    ) -> dict[str, t.Any]:
        self._run_checked(
            ["docker", "stop", container_name],
            timeout=120,
            error_message=f"failed to stop {container_name}",
        )
        removed = False
        if remove:
            self._run_checked(
                ["docker", "rm", "-f", container_name],
                timeout=120,
                error_message=f"failed to remove {container_name}",
            )
            removed = True
        return self._stop_result(slug, container_name=container_name, removed=removed)

    def _write_compose_file(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> Path:
        compose_file = self._compose_file_path(manifest.slug)
        compose_file.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=driver_support.COMPOSE_RUNTIME_DIR_MODE,
        )
        os.chmod(compose_file.parent, driver_support.COMPOSE_RUNTIME_DIR_MODE)
        payload = self._compose_payload(manifest, container_name=container_name)
        compose_file.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        os.chmod(compose_file, driver_support.COMPOSE_RUNTIME_FILE_MODE)
        return compose_file

    def _compose_payload(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> dict[str, t.Any]:
        resolved_runtime = runtime_resolution.resolve_backend_runtime(manifest)
        service_name = self._compose_service_name(manifest.slug)
        service: dict[str, t.Any] = {
            "image": resolved_runtime.image,
            "container_name": container_name,
            "restart": "no",
            "working_dir": manifest.agent.working_dir,
            "labels": self._orchestra_labels(manifest),
            "environment": self._compose_environment(
                manifest,
                resolved_runtime,
                container_name=container_name,
            ),
            "healthcheck": self._compose_healthcheck(manifest, container_name=container_name),
            "volumes": self._compose_volumes(
                manifest,
                resolved_runtime,
                container_name=container_name,
            ),
            "command": list(resolved_runtime.command),
        }
        if resolved_runtime.entrypoint:
            service["entrypoint"] = resolved_runtime.entrypoint
        return {"services": {service_name: service}}

    def _orchestra_labels(self, manifest: manifest_module.AgentManifest) -> dict[str, str]:
        return {
            "orchestra.agent_slug": manifest.slug,
            "orchestra.backend_type": manifest.backend.type,
        }

    def _compose_environment(
        self,
        manifest: manifest_module.AgentManifest,
        resolved_runtime: runtime_resolution.ResolvedRuntimeConfig,
        *,
        container_name: str,
    ) -> dict[str, str]:
        environment = {
            "ORCHESTRA_AGENT_SLUG": manifest.slug,
            "ORCHESTRA_AGENT_BACKEND_TYPE": manifest.backend.type,
            "ORCHESTRA_AGENT_HTTP_ENDPOINT": manifest.resolve_http_endpoint(
                container_name=container_name
            ),
            "ORCHESTRA_AGENT_WORKING_DIR": manifest.agent.working_dir,
            "ORCHESTRA_AGENT_ALLOWED_PEER_AGENT_SLUGS": ",".join(
                manifest.agent.allowed_peer_agent_slugs
            ),
            "ORCHESTRA_AGENT_MANIFESTS_DIR": self.manifest_mount_path,
            "ORCHESTRA_AGENT_MANIFEST": self._container_manifest_path(manifest),
        }
        if manifest.agent.system_prompt_file:
            environment["ORCHESTRA_AGENT_SYSTEM_PROMPT_FILE"] = manifest.agent.system_prompt_file
        environment.update(
            self._render_env(
                manifest,
                resolved_runtime,
                container_name=container_name,
            )
        )
        return environment

    def _compose_healthcheck(
        self, manifest: manifest_module.AgentManifest, *, container_name: str
    ) -> dict[str, t.Any]:
        return {
            "test": [
                "CMD-SHELL",
                self._healthcheck_command(manifest, container_name=container_name),
            ],
            "interval": "30s",
            "timeout": "5s",
            "start_period": "10s",
            "retries": 3,
        }

    def _compose_volumes(
        self,
        manifest: manifest_module.AgentManifest,
        resolved_runtime: runtime_resolution.ResolvedRuntimeConfig,
        *,
        container_name: str,
    ) -> list[str]:
        volumes = [f"{self.manifests_root}:{self.manifest_mount_path}:ro"]
        for mount in resolved_runtime.mounts:
            volumes.append(self._render_mount_spec(manifest, mount, container_name=container_name))
        return volumes

    def _remove_legacy_container_if_needed(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> None:
        if not self._container_exists(container_name):
            return
        if self._container_matches_compose_service(manifest, container_name=container_name):
            return
        self._run_checked(
            ["docker", "rm", "-f", container_name],
            timeout=120,
            error_message=f"failed to replace {container_name}",
        )

    def _container_matches_compose_service(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> bool:
        labels = self._container_labels(container_name)
        if not labels:
            return False
        return labels.get(
            driver_support.COMPOSE_PROJECT_LABEL
        ) == self.compose_project_name and labels.get(
            driver_support.COMPOSE_SERVICE_LABEL
        ) == self._compose_service_name(manifest.slug)

    def _container_labels(
        self,
        container_name: str,
    ) -> driver_support.LabelMap:
        result = _run(
            ["docker", "inspect", container_name, "--format", "{{json .Config.Labels}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return {}
        raw_labels = json.loads(result.stdout.strip() or "{}")
        if not isinstance(raw_labels, dict):
            return {}
        return {str(key): str(value) for key, value in raw_labels.items()}

    def _healthcheck_command(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> str:
        health_url = self._internal_health_url(manifest, container_name=container_name)
        return (
            "python -c "
            f'"import sys,urllib.request; '
            f"sys.exit(0 if urllib.request.urlopen('{health_url}').status == 200 else 1)\""
        )

    def _ensure_startable(self, manifest: manifest_module.AgentManifest) -> None:
        if manifest.runtime.driver != "docker":
            raise RuntimeError(f"unsupported runtime driver {manifest.runtime.driver!r}")
        if not manifest.is_active:
            raise RuntimeError(f"agent {manifest.slug} is inactive")
        if manifest.manifest_path is None or not manifest.manifest_path.exists():
            raise RuntimeError(f"manifest path is missing or invalid for {manifest.slug}")

    def _container_manifest_path(self, manifest: manifest_module.AgentManifest) -> str:
        assert manifest.manifest_path is not None
        relative_path = manifest.manifest_path.relative_to(self.manifests_root)
        return f"{self.manifest_mount_path}/{relative_path.as_posix()}"

    def _render_env(
        self,
        manifest: manifest_module.AgentManifest,
        resolved_runtime: runtime_resolution.ResolvedRuntimeConfig,
        *,
        container_name: str,
    ) -> dict[str, str]:
        values = {
            "slug": manifest.slug,
            "container_name": container_name,
            "backend_type": manifest.backend.type,
            "working_dir": manifest.agent.working_dir,
        }
        rendered: dict[str, str] = {}
        for key, value in resolved_runtime.env.items():
            rendered[key] = str(value).format(**values)
        for key in resolved_runtime.env_passthrough:
            host_value = os.getenv(key)
            if host_value is not None and host_value != "":
                rendered[key] = host_value
        return rendered

    def _render_mount_spec(
        self,
        manifest: manifest_module.AgentManifest,
        mount: manifest_module.RuntimeMount,
        *,
        container_name: str,
    ) -> str:
        values = {
            "slug": manifest.slug,
            "container_name": container_name,
            "backend_type": manifest.backend.type,
        }
        source = self._resolve_mount_source(manifest, mount, values)
        target = str(mount.target).format(**values)
        return f"{source}:{target}:{mount.mode}"

    def _resolve_mount_source(
        self,
        manifest: manifest_module.AgentManifest,
        mount: manifest_module.RuntimeMount,
        values: dict[str, str],
    ) -> str:
        source = str(mount.source).format(**values)
        if mount.type != "bind":
            return source
        return str(self._resolve_bind_source_path(manifest, source))

    def _resolve_bind_source_path(
        self,
        manifest: manifest_module.AgentManifest,
        source: str,
    ) -> Path:
        source_path = Path(source)
        if source_path.is_absolute():
            resolved_path = source_path
        else:
            if manifest.manifest_path is None:
                raise RuntimeError(
                    f"cannot resolve relative bind mount {source!r} without manifest path"
                )
            resolved_path = (manifest.manifest_path.parent / source_path).resolve()
        if not resolved_path.exists():
            raise RuntimeError(f"bind mount source does not exist: {resolved_path}")
        return resolved_path

    def _container_exists(self, container_name: str) -> bool:
        result = _run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{container_name}$",
                "--format",
                "{{.Names}}",
            ],
            timeout=30,
        )
        if result.returncode != 0:
            return False
        return container_name in {
            line.strip() for line in result.stdout.splitlines() if line.strip()
        }

    def _image_exists(self, image: str) -> bool:
        result = _run(["docker", "image", "inspect", image], timeout=60)
        return result.returncode == 0

    def _ensure_image_available(self, image: str) -> None:
        from core.orchestra_agents import _docker_runtime_specs as runtime_specs

        normalized = str(image or "").strip()
        if not normalized or self._image_exists(normalized):
            return
        dockerfile_name = runtime_specs.local_runtime_dockerfile(normalized)
        if dockerfile_name is None:
            return
        if not self.auto_build_local_images:
            raise RuntimeError(f"docker image {normalized} is missing and auto-build is disabled")
        dockerfile_path = (self._build_context_root / dockerfile_name).resolve()
        if not dockerfile_path.exists():
            raise RuntimeError(
                f"docker image {normalized} is missing and build dockerfile was not found: {dockerfile_path}"
            )
        self._run_checked(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile_path),
                "-t",
                normalized,
                str(self._build_context_root),
            ],
            timeout=1800,
            error_message=f"failed to build local runtime image {normalized}",
        )

    def _container_running(self, container_name: str) -> bool:
        result = _run(
            ["docker", "ps", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return False
        return container_name in {
            line.strip() for line in result.stdout.splitlines() if line.strip()
        }

    def _probe_health(self, endpoint: str) -> dict[str, t.Any]:
        from urllib import error as urlerror

        url = f"{endpoint.rstrip('/')}/healthz"
        try:
            payload = self._read_health_payload(url)
        except urlerror.HTTPError as exc:
            return {
                "ok": False,
                "status_code": exc.code,
                "error": exc.reason,
            }
        except Exception as exc:
            return {
                "ok": False,
                "status_code": None,
                "error": str(exc),
            }
        if isinstance(payload, dict):
            return {
                "ok": True,
                "status_code": 200,
                "payload": payload,
            }
        return {
            "ok": True,
            "status_code": 200,
            "payload": {"raw": payload},
        }

    def _read_health_payload(self, url: str) -> t.Any:
        from urllib import request as urlrequest

        with urlrequest.urlopen(url, timeout=self.health_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def _internal_health_url(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> str:
        endpoint = manifest.resolve_http_endpoint(container_name=container_name)
        port = _endpoint_port(endpoint)
        if port is None:
            port = 443 if endpoint.startswith("https://") else 80
        return f"http://127.0.0.1:{port}/healthz"

    def _start_existing(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> dict[str, t.Any]:
        if not self._container_running(container_name):
            self._run_checked(
                ["docker", "start", container_name],
                timeout=120,
                error_message=f"failed to start {container_name}",
            )
        status = self.status(manifest)
        status["message"] = "container already exists"
        return status

    def _start_new(
        self,
        manifest: manifest_module.AgentManifest,
        *,
        container_name: str,
    ) -> dict[str, t.Any]:
        resolved_runtime = runtime_resolution.resolve_backend_runtime(manifest)
        self._ensure_image_available(resolved_runtime.image)
        result = self._run_checked(
            self._build_run_command(manifest, container_name=container_name),
            timeout=300,
            error_message=f"failed to start {manifest.slug}",
        )
        status = self.status(manifest)
        status["container_id"] = result.stdout.strip()
        return status

    def _run_checked(
        self,
        command: list[str],
        *,
        timeout: int,
        error_message: str,
    ) -> subprocess.CompletedProcess[str]:
        result = _run(command, timeout=timeout)
        if result.returncode == 0:
            return result
        raise RuntimeError(result.stderr.strip() or error_message)
