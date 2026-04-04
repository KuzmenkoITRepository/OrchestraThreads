"""Docker-backed runtime driver for manifest-defined agents."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .manifest import AgentManifest, RuntimeMount

_LOCAL_RUNTIME_IMAGE_DOCKERFILES = {
    "orchestra-agent-runtime:latest": "Dockerfile.agent_runtime",
    "orchestra-agent-mux-runtime:latest": "Dockerfile.agent_mux_runtime",
}


def _run(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class DockerDriver:
    """Start, stop, and inspect agent containers through Docker."""

    def __init__(
        self,
        *,
        manifests_root: str | Path,
        container_name_prefix: Optional[str] = None,
        default_network: Optional[str] = None,
        manifest_mount_path: Optional[str] = None,
        health_timeout_seconds: Optional[float] = None,
        build_context_root: Optional[str | Path] = None,
        auto_build_local_images: Optional[bool] = None,
    ) -> None:
        self.manifests_root = Path(manifests_root).expanduser().resolve()
        self.container_name_prefix = str(
            container_name_prefix
            or os.getenv("ORCHESTRA_AGENTS_CONTAINER_NAME_PREFIX")
            or "orchestra-agent-"
        )
        self.default_network = str(
            default_network
            or os.getenv("ORCHESTRA_AGENTS_DOCKER_NETWORK")
            or ""
        ).strip() or None
        self.manifest_mount_path = str(
            manifest_mount_path
            or os.getenv("ORCHESTRA_AGENTS_MANIFEST_MOUNT_PATH")
            or "/orchestra/agents"
        ).rstrip("/")
        self.health_timeout_seconds = max(
            0.2,
            float(health_timeout_seconds or os.getenv("ORCHESTRA_AGENTS_HEALTH_TIMEOUT_SECONDS", "2")),
        )
        auto_build_value = auto_build_local_images
        if auto_build_value is None:
            normalized = str(os.getenv("ORCHESTRA_AGENTS_AUTO_BUILD_LOCAL_IMAGES", "true")).strip().lower()
            auto_build_value = normalized not in {"0", "false", "no", "off"}
        self.auto_build_local_images = bool(auto_build_value)
        self.build_context_root = Path(
            build_context_root or os.getenv("ORCHESTRA_AGENTS_IMAGE_BUILD_CONTEXT") or self.manifests_root.parent
        ).expanduser().resolve()

    def container_name(self, slug: str) -> str:
        return f"{self.container_name_prefix}{str(slug).strip()}"

    def start(self, manifest: AgentManifest) -> dict[str, Any]:
        self._ensure_startable(manifest)
        container_name = self.container_name(manifest.slug)
        if self._container_exists(container_name):
            if not self._container_running(container_name):
                result = _run(["docker", "start", container_name], timeout=120)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or f"failed to start {container_name}")
            status = self.status(manifest)
            status["message"] = "container already exists"
            return status

        self._ensure_image_available(manifest.runtime.image)
        run_cmd = self._build_run_command(manifest, container_name=container_name)
        result = _run(run_cmd, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"failed to start {manifest.slug}")
        status = self.status(manifest)
        status["container_id"] = result.stdout.strip()
        return status

    def stop(self, slug: str, *, remove: bool = False) -> dict[str, Any]:
        container_name = self.container_name(slug)
        if not self._container_exists(container_name):
            return {
                "slug": slug,
                "container_name": container_name,
                "exists": False,
                "running": False,
                "removed": False,
            }
        result = _run(["docker", "stop", container_name], timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"failed to stop {container_name}")
        removed = False
        if remove:
            rm_result = _run(["docker", "rm", "-f", container_name], timeout=120)
            if rm_result.returncode != 0:
                raise RuntimeError(rm_result.stderr.strip() or f"failed to remove {container_name}")
            removed = True
        return {
            "slug": slug,
            "container_name": container_name,
            "exists": not removed,
            "running": False,
            "removed": removed,
        }

    def restart(self, manifest: AgentManifest) -> dict[str, Any]:
        self._ensure_startable(manifest)
        container_name = self.container_name(manifest.slug)
        if not self._container_exists(container_name):
            return self.start(manifest)
        result = _run(["docker", "restart", container_name], timeout=180)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"failed to restart {container_name}")
        return self.status(manifest)

    def status(self, manifest_or_slug: AgentManifest | str) -> dict[str, Any]:
        manifest = manifest_or_slug if isinstance(manifest_or_slug, AgentManifest) else None
        slug = manifest.slug if manifest is not None else str(manifest_or_slug).strip()
        container_name = self.container_name(slug)
        inspect_result = _run(
            ["docker", "inspect", container_name, "--format", "{{json .State}}"],
            timeout=30,
        )
        endpoint = manifest.resolve_http_endpoint(container_name=container_name) if manifest is not None else None
        if inspect_result.returncode != 0:
            return {
                "slug": slug,
                "container_name": container_name,
                "exists": False,
                "running": False,
                "healthy": False,
                "backend_type": manifest.backend.type if manifest is not None else None,
                "http_endpoint": endpoint,
                "docker_status": None,
                "health_status": None,
                "started_at": None,
                "last_error": inspect_result.stderr.strip() or None,
            }

        state = json.loads(inspect_result.stdout.strip() or "{}")
        running = bool(state.get("Running"))
        health_status = None
        healthy = False
        last_error = str(state.get("Error") or "").strip() or None
        docker_health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        docker_health_status = str(docker_health.get("Status") or "").strip().lower()
        if running and docker_health_status == "healthy":
            healthy = True
            health_status = {
                "ok": True,
                "status_code": 200,
                "source": "docker",
                "status": docker_health_status,
            }
        elif running and docker_health_status:
            health_status = {
                "ok": False,
                "status_code": None,
                "source": "docker",
                "status": docker_health_status,
            }
            if not last_error:
                last_error = docker_health_status
        elif running and endpoint:
            health_status = self._probe_health(endpoint)
            healthy = bool(health_status.get("ok"))
            if not healthy and not last_error:
                last_error = str(health_status.get("error") or "").strip() or None

        return {
            "slug": slug,
            "container_name": container_name,
            "exists": True,
            "running": running,
            "healthy": healthy,
            "backend_type": manifest.backend.type if manifest is not None else None,
            "http_endpoint": endpoint,
            "docker_status": str(state.get("Status") or "").strip() or None,
            "health_status": health_status,
            "started_at": state.get("StartedAt"),
            "last_error": last_error,
        }

    def _build_run_command(self, manifest: AgentManifest, *, container_name: str) -> list[str]:
        health_url = self._internal_health_url(manifest, container_name=container_name)
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
            f"ORCHESTRA_AGENT_MANIFESTS_DIR={self.manifest_mount_path}",
            "--health-cmd",
            (
                "python -c "
                f"\"import sys,urllib.request; "
                f"sys.exit(0 if urllib.request.urlopen('{health_url}').status == 200 else 1)\""
            ),
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

        container_manifest_path = self._container_manifest_path(manifest)
        command.extend(["-e", f"ORCHESTRA_AGENT_MANIFEST={container_manifest_path}"])
        if manifest.agent.system_prompt_file:
            command.extend(["-e", f"ORCHESTRA_AGENT_SYSTEM_PROMPT_FILE={manifest.agent.system_prompt_file}"])

        for key, value in self._render_env(manifest, container_name=container_name).items():
            command.extend(["-e", f"{key}={value}"])

        for mount in manifest.runtime.mounts:
            command.extend(["-v", self._render_mount_spec(manifest, mount, container_name=container_name)])

        if manifest.runtime.entrypoint:
            command.extend(["--entrypoint", manifest.runtime.entrypoint])

        command.append(manifest.runtime.image)
        command.extend(manifest.runtime.command)
        return command

    def _ensure_startable(self, manifest: AgentManifest) -> None:
        if manifest.runtime.driver != "docker":
            raise RuntimeError(f"unsupported runtime driver {manifest.runtime.driver!r}")
        if not manifest.is_active:
            raise RuntimeError(f"agent {manifest.slug} is inactive")
        if manifest.manifest_path is None:
            raise RuntimeError(f"manifest path is missing for {manifest.slug}")
        if not manifest.manifest_path.exists():
            raise RuntimeError(f"manifest file does not exist for {manifest.slug}")

    def _container_manifest_path(self, manifest: AgentManifest) -> str:
        assert manifest.manifest_path is not None
        relative_path = manifest.manifest_path.relative_to(self.manifests_root)
        return f"{self.manifest_mount_path}/{relative_path.as_posix()}"

    def _render_env(self, manifest: AgentManifest, *, container_name: str) -> dict[str, str]:
        values = {
            "slug": manifest.slug,
            "container_name": container_name,
            "backend_type": manifest.backend.type,
        }
        rendered = {
            key: str(value).format(**values)
            for key, value in manifest.runtime.env.items()
        }
        for key in manifest.runtime.env_passthrough:
            host_value = os.getenv(key)
            if host_value is not None:
                rendered[key] = host_value
        return rendered

    def _render_mount_spec(self, manifest: AgentManifest, mount: RuntimeMount, *, container_name: str) -> str:
        values = {
            "slug": manifest.slug,
            "container_name": container_name,
            "backend_type": manifest.backend.type,
        }
        source = str(mount.source).format(**values)
        target = str(mount.target).format(**values)
        if mount.type == "bind":
            source_path = Path(source)
            if not source_path.is_absolute():
                if manifest.manifest_path is None:
                    raise RuntimeError(f"cannot resolve relative bind mount {source!r} without manifest path")
                source_path = (manifest.manifest_path.parent / source_path).resolve()
            if not source_path.exists():
                raise RuntimeError(f"bind mount source does not exist: {source_path}")
            source = str(source_path)
        return f"{source}:{target}:{mount.mode}"

    def _container_exists(self, container_name: str) -> bool:
        result = _run(
            ["docker", "ps", "-a", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return False
        return container_name in {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _image_exists(self, image: str) -> bool:
        result = _run(["docker", "image", "inspect", image], timeout=60)
        return result.returncode == 0

    def _ensure_image_available(self, image: str) -> None:
        normalized = str(image or "").strip()
        if not normalized or self._image_exists(normalized):
            return
        dockerfile_name = _LOCAL_RUNTIME_IMAGE_DOCKERFILES.get(normalized)
        if dockerfile_name is None:
            return
        if not self.auto_build_local_images:
            raise RuntimeError(
                f"docker image {normalized} is missing and auto-build is disabled"
            )
        dockerfile_path = (self.build_context_root / dockerfile_name).resolve()
        if not dockerfile_path.exists():
            raise RuntimeError(
                f"docker image {normalized} is missing and build dockerfile was not found: {dockerfile_path}"
            )
        result = _run(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile_path),
                "-t",
                normalized,
                str(self.build_context_root),
            ],
            timeout=1800,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or f"failed to build local runtime image {normalized}"
            )

    def _container_running(self, container_name: str) -> bool:
        result = _run(
            ["docker", "ps", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return False
        return container_name in {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _probe_health(self, endpoint: str) -> dict[str, Any]:
        url = f"{endpoint.rstrip('/')}/healthz"
        try:
            with urllib.request.urlopen(url, timeout=self.health_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
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
        except urllib.error.HTTPError as exc:
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

    def _internal_health_url(self, manifest: AgentManifest, *, container_name: str) -> str:
        endpoint = manifest.resolve_http_endpoint(container_name=container_name)
        parsed = urlparse(endpoint)
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return f"http://127.0.0.1:{port}/healthz"
