"""Environment-backed configuration for Telegram MCP using Telethon auth."""

from __future__ import annotations

import os
from dataclasses import dataclass

from telegram_mcp.config_parsers import parse_chat_id, parse_float_env, parse_int_env


@dataclass(frozen=True)
class TelegramAuth:
    """Telethon authentication credentials."""

    api_id: int
    api_hash: str
    session_string: str | None


@dataclass(frozen=True)
class TelegramDefaults:
    """Default recipient and retry settings."""

    default_recipient: str
    timeout_seconds: float
    max_retries: int
    log_level: str


@dataclass(frozen=True)
class TelegramMCPConfig:
    """Telegram MCP settings loaded from environment variables."""

    auth: TelegramAuth
    defaults: TelegramDefaults
    chat_id_ivan: int

    def resolve_chat_id(self, recipient: str | None) -> int:
        """Resolve a recipient alias to a Telegram chat ID."""
        alias = (recipient or self.defaults.default_recipient).strip().lower()
        if alias == "ivan":
            return self.chat_id_ivan
        raise ValueError(f"Unknown recipient alias '{alias}'. Available aliases: ivan")


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return value.strip()


def load_config() -> TelegramMCPConfig:
    """Load Telegram MCP config from environment variables."""
    auth = TelegramAuth(
        api_id=int(_require_env("TELEGRAM_API_ID")),
        api_hash=_require_env("TELEGRAM_API_HASH"),
        session_string=os.getenv("TELEGRAM_SESSION_STRING", "").strip() or None,
    )
    recipient = os.getenv("TELEGRAM_DEFAULT_RECIPIENT", "ivan").strip().lower()
    if not recipient:
        raise ValueError("TELEGRAM_DEFAULT_RECIPIENT must not be empty")
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if not log_level:
        raise ValueError("LOG_LEVEL must not be empty")
    defaults = TelegramDefaults(
        default_recipient=recipient,
        timeout_seconds=parse_float_env(
            os.getenv("TELEGRAM_TIMEOUT_SECONDS", "10.0"), "TELEGRAM_TIMEOUT_SECONDS"
        ),
        max_retries=parse_int_env(os.getenv("TELEGRAM_MAX_RETRIES", "3"), "TELEGRAM_MAX_RETRIES"),
        log_level=log_level,
    )
    return TelegramMCPConfig(
        auth=auth,
        defaults=defaults,
        chat_id_ivan=parse_chat_id(_require_env("TELEGRAM_CHAT_ID_IVAN")),
    )
