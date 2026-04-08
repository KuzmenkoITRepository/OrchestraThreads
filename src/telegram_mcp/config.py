"""Environment-backed configuration for Telegram MCP HTTP proxy."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramDefaults:
    """Default recipient and log level."""

    default_recipient: str
    log_level: str


@dataclass(frozen=True)
class TelegramMCPConfig:
    """Telegram MCP settings loaded from environment variables."""

    telegram_events_url: str
    defaults: TelegramDefaults
    chat_id_ivan: int

    def resolve_chat_id(self, recipient: str | None) -> int:
        """Resolve a recipient alias to a Telegram chat ID."""
        alias = (recipient or self.defaults.default_recipient).strip().lower()
        if alias == "ivan":
            return self.chat_id_ivan
        raise ValueError(
            f"Unknown recipient alias '{alias}'. Available: ivan",
        )


def _require_env(key: str) -> str:
    env_value = os.getenv(key)
    if env_value is None or not env_value.strip():
        raise ValueError(
            f"Missing required environment variable: {key}",
        )
    return env_value.strip()


def load_config() -> TelegramMCPConfig:
    """Load Telegram MCP config from environment variables."""
    recipient = os.getenv("TELEGRAM_DEFAULT_RECIPIENT", "ivan").strip().lower()
    if not recipient:
        raise ValueError("TELEGRAM_DEFAULT_RECIPIENT must not be empty")
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if not log_level:
        raise ValueError("LOG_LEVEL must not be empty")
    chat_id_raw = _require_env("TELEGRAM_CHAT_ID_IVAN")
    return TelegramMCPConfig(
        telegram_events_url=_require_env("TELEGRAM_EVENTS_URL"),
        defaults=TelegramDefaults(
            default_recipient=recipient,
            log_level=log_level,
        ),
        chat_id_ivan=int(chat_id_raw),
    )
