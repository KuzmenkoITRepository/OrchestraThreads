from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramBotMCPConfig:
    listener_url: str
    listener_api_token: str
    timeout_seconds: float
    log_level: str


def load_config() -> TelegramBotMCPConfig:
    raw_listener_url = os.getenv("TELEGRAM_BOT_LISTENER_URL") or "http://127.0.0.1:8791"
    listener_url = str(raw_listener_url).rstrip("/")
    timeout_seconds = float(os.getenv("TELEGRAM_BOT_MCP_TIMEOUT_SECONDS", "10"))
    log_level = _log_level()
    return TelegramBotMCPConfig(
        listener_url=listener_url,
        listener_api_token=_listener_api_token(),
        timeout_seconds=max(1.0, timeout_seconds),
        log_level=log_level,
    )


def _log_level() -> str:
    raw_level = os.getenv("LOG_LEVEL") or "INFO"
    return str(raw_level).strip().upper() or "INFO"


def _listener_api_token() -> str:
    token = str(os.getenv("TELEGRAM_BOT_LISTENER_API_TOKEN") or "").strip()
    if token:
        return token
    raise RuntimeError("TELEGRAM_BOT_LISTENER_API_TOKEN must be set")
