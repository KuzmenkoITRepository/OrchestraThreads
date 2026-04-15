from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.telegram_events import agent_registry_support


class RegistrationStatus(StrEnum):
    REGISTERED = "registered"
    DUPLICATE = "duplicate"
    REMAPPED = "remapped"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class AgentRegistration:
    agent_slug: str
    telegram_mcp_url: str
    events_url: str


@dataclass(frozen=True)
class RegistrationResult:
    status: RegistrationStatus
    agent_slug: str
    telegram_mcp_url: str
    events_url: str
    previous_telegram_mcp_url: str | None = None
    previous_events_url: str | None = None
    conflicting_agent_slug: str | None = None

    @property
    def is_conflict(self) -> bool:
        return self.status is RegistrationStatus.CONFLICT

    @property
    def is_remap(self) -> bool:
        return self.status is RegistrationStatus.REMAPPED

    @property
    def is_duplicate(self) -> bool:
        return self.status is RegistrationStatus.DUPLICATE


@dataclass
class TelegramAgentRegistry:
    _by_slug: dict[str, AgentRegistration]
    _by_mcp_url: dict[str, str]

    def __init__(self) -> None:
        self._by_slug = {}
        self._by_mcp_url = {}

    def register(self, agent_slug: str, telegram_mcp_url: str) -> RegistrationResult:
        normalized_slug = agent_registry_support.normalize_slug(agent_slug)
        normalized_mcp_url = agent_registry_support.normalize_mcp_url(telegram_mcp_url)
        conflict = agent_registry_support.conflict_result(
            self._by_mcp_url,
            normalized_slug,
            normalized_mcp_url,
        )
        if conflict is not None:
            return conflict
        existing_registration = self._by_slug.get(normalized_slug)
        if existing_registration is None:
            return agent_registry_support.register_new(
                self._by_slug,
                self._by_mcp_url,
                normalized_slug,
                normalized_mcp_url,
            )
        if existing_registration.telegram_mcp_url == normalized_mcp_url:
            return agent_registry_support.duplicate_result(normalized_slug, normalized_mcp_url)
        return agent_registry_support.remap_registration(
            self._by_slug,
            self._by_mcp_url,
            existing_registration,
            normalized_slug,
            normalized_mcp_url,
        )

    def get_slug_for_mcp_url(self, telegram_mcp_url: str) -> str | None:
        normalized_mcp_url = agent_registry_support.normalize_mcp_url(telegram_mcp_url)
        return self._by_mcp_url.get(normalized_mcp_url)

    def get_events_url_for_mcp_url(self, telegram_mcp_url: str) -> str | None:
        normalized_mcp_url = agent_registry_support.normalize_mcp_url(telegram_mcp_url)
        slug = self._by_mcp_url.get(normalized_mcp_url)
        if slug is None:
            return None
        return self._by_slug[slug].events_url

    def get_registration_for_slug(self, agent_slug: str) -> AgentRegistration | None:
        normalized_slug = agent_registry_support.normalize_slug(agent_slug)
        return self._by_slug.get(normalized_slug)
