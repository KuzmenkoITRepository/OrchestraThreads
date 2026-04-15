"""HTTP endpoint and health helpers for launch specs."""

from __future__ import annotations

from urllib.parse import SplitResult, urlsplit

from core.orchestra_agents.manifest import AgentManifest


def resolve_http_endpoint(manifest: AgentManifest, *, container_name: str) -> str:
    """Render and validate manifest HTTP endpoint template."""

    try:
        endpoint = manifest.agent.http_endpoint.format(
            slug=manifest.slug,
            container_name=container_name,
        )
    except KeyError as error:
        raise RuntimeError(
            f"invalid agent.http_endpoint template for {manifest.slug}: missing {error.args[0]!r}"
        ) from error
    except ValueError as error:
        raise RuntimeError(f"invalid agent.http_endpoint template for {manifest.slug}") from error
    normalized = endpoint.strip()
    if not normalized:
        raise RuntimeError(f"agent {manifest.slug} is missing agent.http_endpoint")
    _validate_endpoint_scheme(urlsplit(normalized), manifest.slug)
    return normalized


def resolve_internal_health_url(manifest: AgentManifest, *, container_name: str) -> str:
    """Return in-container health probe URL matching docker parity."""

    endpoint = resolve_http_endpoint(manifest, container_name=container_name)
    port = _endpoint_port(endpoint) or _default_health_port(endpoint)
    return f"http://127.0.0.1:{port}/healthz"


def resolve_healthcheck_command(manifest: AgentManifest, *, container_name: str) -> str:
    """Return healthcheck command matching current docker driver behavior."""

    health_url = resolve_internal_health_url(manifest, container_name=container_name)
    return (
        'python -c "import sys,urllib.request; '
        f"sys.exit(0 if urllib.request.urlopen('{health_url}').status == 200 else 1)\""
    )


def _default_health_port(endpoint: str) -> int:
    return 443 if endpoint.startswith("https://") else 80


def _endpoint_port(endpoint: str) -> int | None:
    without_scheme = endpoint.split("://", maxsplit=1)[-1]
    host_and_path = without_scheme.split("/", maxsplit=1)[0]
    if ":" not in host_and_path:
        return None
    raw_port = host_and_path.rsplit(":", maxsplit=1)[-1].strip()
    if not raw_port.isdigit():
        raise RuntimeError(f"invalid agent.http_endpoint port: {endpoint!r}")
    return int(raw_port)


def _validate_endpoint_scheme(parsed: SplitResult, slug: str) -> None:
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"unsupported agent.http_endpoint scheme for {slug}: {parsed.scheme!r}")
