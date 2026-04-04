"""Environment-backed configuration for Telegram MCP using Telethon auth."""

from __future__ import annotations

import os
from typing import Optional


class TelegramMCPConfig:
    """Load and validate Telegram MCP settings from environment variables.

    Authentication uses Telethon user-session credentials:
    TELEGRAM_API_ID, TELEGRAM_API_HASH, and optional TELEGRAM_SESSION_STRING.
    """

    def __init__(self) -> None:
        self.api_id: int = int(self._require_env("TELEGRAM_API_ID"))
        self.api_hash: str = self._require_env("TELEGRAM_API_HASH")
        self.session_string: Optional[str] = (
            os.getenv("TELEGRAM_SESSION_STRING", "").strip() or None
        )
        chat_id_ivan = self._parse_chat_id(self._require_env("TELEGRAM_CHAT_ID_IVAN"))
        if chat_id_ivan is None:
            raise ValueError("TELEGRAM_CHAT_ID_IVAN must be a valid integer chat ID")
        self.chat_id_ivan: int = chat_id_ivan

        self.default_recipient: str = os.getenv("TELEGRAM_DEFAULT_RECIPIENT", "ivan")
        if not self.default_recipient.strip():
            raise ValueError("TELEGRAM_DEFAULT_RECIPIENT must not be empty")
        self.default_recipient = self.default_recipient.strip().lower()

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        if not self.log_level.strip():
            raise ValueError("LOG_LEVEL must not be empty")
        self.log_level = self.log_level.strip().upper()

        self.timeout_seconds: float = self._parse_float_env(
            "TELEGRAM_TIMEOUT_SECONDS", "10.0"
        )
        self.max_retries: int = self._parse_int_env("TELEGRAM_MAX_RETRIES", "3")

    def resolve_chat_id(self, recipient: Optional[str]) -> int:
        """Resolve a recipient alias to a Telegram chat ID."""
        alias = (recipient or self.default_recipient).strip().lower()

        if alias == "ivan":
            return self.chat_id_ivan

        raise ValueError(f"Unknown recipient alias '{alias}'. Available aliases: ivan")

    @staticmethod
    def _require_env(key: str) -> str:
        """Get a required environment variable or raise."""
        value = os.getenv(key)
        if value is None or not value.strip():
            raise ValueError(f"Missing required environment variable: {key}")
        return value.strip()

    @staticmethod
    def _parse_chat_id(value: Optional[str]) -> Optional[int]:
        """Parse a Telegram chat ID from an environment value."""
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            return None

        try:
            return int(stripped)
        except ValueError as exc:
            raise ValueError(f"Invalid Telegram chat ID: {value!r}") from exc

    @staticmethod
    def _parse_float_env(key: str, default: str) -> float:
        value = os.getenv(key, default)
        if value is None or not value.strip():
            raise ValueError(f"{key} must not be empty")
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{key} must be a valid float") from exc

    @staticmethod
    def _parse_int_env(key: str, default: str) -> int:
        value = os.getenv(key, default)
        if value is None or not value.strip():
            raise ValueError(f"{key} must not be empty")
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{key} must be a valid integer") from exc
