from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.telegram_events.agent_registry import AgentRegistration, RegistrationResult


def normalize_slug(agent_slug: str) -> str:
    normalized = str(agent_slug or "").strip()
    if not normalized:
        raise ValueError("agent_slug is required")
    return normalized


def normalize_mcp_url(telegram_mcp_url: str) -> str:
    normalized = str(telegram_mcp_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("telegram_mcp_url is required")
    return normalized


def events_url_for_mcp_url(normalized_mcp_url: str) -> str:
    return f"{normalized_mcp_url.removesuffix('/mcp')}/events/telegram"


def conflict_result(
    by_mcp_url: dict[str, str],
    normalized_slug: str,
    normalized_mcp_url: str,
) -> RegistrationResult | None:
    from core.telegram_events.agent_registry import RegistrationResult, RegistrationStatus

    current_slug = by_mcp_url.get(normalized_mcp_url)
    if current_slug is None or current_slug == normalized_slug:
        return None
    return RegistrationResult(
        status=RegistrationStatus.CONFLICT,
        agent_slug=normalized_slug,
        telegram_mcp_url=normalized_mcp_url,
        events_url=events_url_for_mcp_url(normalized_mcp_url),
        conflicting_agent_slug=current_slug,
    )


def duplicate_result(normalized_slug: str, normalized_mcp_url: str) -> RegistrationResult:
    from core.telegram_events.agent_registry import RegistrationResult, RegistrationStatus

    return RegistrationResult(
        status=RegistrationStatus.DUPLICATE,
        agent_slug=normalized_slug,
        telegram_mcp_url=normalized_mcp_url,
        events_url=events_url_for_mcp_url(normalized_mcp_url),
    )


def register_new(
    by_slug: dict[str, AgentRegistration],
    by_mcp_url: dict[str, str],
    normalized_slug: str,
    normalized_mcp_url: str,
) -> RegistrationResult:
    from core.telegram_events.agent_registry import (
        AgentRegistration,
        RegistrationResult,
        RegistrationStatus,
    )

    registration = AgentRegistration(
        agent_slug=normalized_slug,
        telegram_mcp_url=normalized_mcp_url,
        events_url=events_url_for_mcp_url(normalized_mcp_url),
    )
    by_slug[normalized_slug] = registration
    by_mcp_url[normalized_mcp_url] = normalized_slug
    return RegistrationResult(
        status=RegistrationStatus.REGISTERED,
        agent_slug=normalized_slug,
        telegram_mcp_url=normalized_mcp_url,
        events_url=registration.events_url,
    )


def remap_registration(
    by_slug: dict[str, AgentRegistration],
    by_mcp_url: dict[str, str],
    existing_registration: AgentRegistration,
    normalized_slug: str,
    normalized_mcp_url: str,
) -> RegistrationResult:
    from core.telegram_events.agent_registry import (
        AgentRegistration,
        RegistrationResult,
        RegistrationStatus,
    )

    previous_mcp_url = existing_registration.telegram_mcp_url
    previous_events_url = existing_registration.events_url
    next_registration = AgentRegistration(
        agent_slug=normalized_slug,
        telegram_mcp_url=normalized_mcp_url,
        events_url=events_url_for_mcp_url(normalized_mcp_url),
    )
    by_mcp_url.pop(previous_mcp_url, None)
    by_slug[normalized_slug] = next_registration
    by_mcp_url[normalized_mcp_url] = normalized_slug
    return RegistrationResult(
        status=RegistrationStatus.REMAPPED,
        agent_slug=normalized_slug,
        telegram_mcp_url=normalized_mcp_url,
        events_url=next_registration.events_url,
        previous_telegram_mcp_url=previous_mcp_url,
        previous_events_url=previous_events_url,
    )
