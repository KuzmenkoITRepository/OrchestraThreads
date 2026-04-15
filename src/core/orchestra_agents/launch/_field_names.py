"""Container and compose naming helpers for launch specs."""


def resolve_container_name(*, slug: str, prefix: str) -> str:
    """Return runtime container name for an agent slug."""

    return f"{prefix}{str(slug).strip()}"


def resolve_compose_service_name(slug: str, *, prefix: str = "agent-") -> str:
    """Return compose service name matching current docker driver parity."""

    normalized_slug = str(slug).strip().replace("_", "-")
    return f"{prefix}{normalized_slug}"
