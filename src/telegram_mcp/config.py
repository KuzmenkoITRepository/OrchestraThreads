from __future__ import annotations

import os
from dataclasses import dataclass

from telegram_mcp.config_parsers import parse_chat_id

_DEFAULT_RECIPIENT = "ivan"
_DEFAULT_LOG_LEVEL = "INFO"
_ENV_TELEGRAM_EVENTS_URL = "TELEGRAM_EVENTS_URL"
_ENV_TELEGRAM_CHAT_ID_IVAN = "TELEGRAM_CHAT_ID_IVAN"
_ENV_TELEGRAM_DEFAULT_RECIPIENT = "TELEGRAM_DEFAULT_RECIPIENT"
_ENV_LOG_LEVEL = "LOG_LEVEL"


@dataclass(frozen=True)
class TelegramDefaults:
    default_recipient: str
    log_level: str


@dataclass(frozen=True)
class TelegramMCPConfig:
    telegram_events_url: str
    defaults: TelegramDefaults
    chat_id_ivan: int

    def resolve_chat_id(self, recipient: str | None) -> int:
        alias = (recipient or self.defaults.default_recipient).strip().lower()
        if alias == _DEFAULT_RECIPIENT:
            return self.chat_id_ivan
        raise ValueError(
            f"Unknown recipient alias '{alias}'. Available aliases: {_DEFAULT_RECIPIENT}",
        )


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return value.strip()


def load_config() -> TelegramMCPConfig:
    recipient = os.getenv(_ENV_TELEGRAM_DEFAULT_RECIPIENT, _DEFAULT_RECIPIENT).strip().lower()
    if not recipient:
        raise ValueError(f"{_ENV_TELEGRAM_DEFAULT_RECIPIENT} must not be empty")
    log_level = os.getenv(_ENV_LOG_LEVEL, _DEFAULT_LOG_LEVEL).strip().upper()
    if not log_level:
        raise ValueError(f"{_ENV_LOG_LEVEL} must not be empty")
    return TelegramMCPConfig(
        telegram_events_url=_require_env(_ENV_TELEGRAM_EVENTS_URL),
        defaults=TelegramDefaults(
            default_recipient=recipient,
            log_level=log_level,
        ),
        chat_id_ivan=parse_chat_id(_require_env(_ENV_TELEGRAM_CHAT_ID_IVAN)),
    )
