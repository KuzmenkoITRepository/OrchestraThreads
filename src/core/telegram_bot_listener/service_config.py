from __future__ import annotations

import logging
import os
import sys

from core.telegram_bot_listener.service import TelegramBotListenerConfig, TelegramBotListenerService


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_service(logger: logging.Logger) -> TelegramBotListenerService:
    return TelegramBotListenerService(_load_config(logger))


def _load_config(logger: logging.Logger) -> TelegramBotListenerConfig:
    return TelegramBotListenerConfig(
        host=os.getenv("TELEGRAM_BOT_LISTENER_HOST", "0.0.0.0"),
        port=_int_env("TELEGRAM_BOT_LISTENER_PORT", "8791", logger),
        bot_token=_required_env("TELEGRAM_BOT_TOKEN", logger),
        allowed_user_ids=frozenset(_allowed_user_ids(logger)),
        api_token=_required_env("TELEGRAM_BOT_LISTENER_API_TOKEN", logger),
        events_engine_url=os.getenv("EVENTS_ENGINE_URL", "http://events-engine:8789"),
        target_agent_slug=os.getenv("TARGET_AGENT_SLUG", "secretary"),
        state_file=os.getenv(
            "TELEGRAM_BOT_STATE_FILE",
            "data/telegram_bot_listener/state.json",
        ),
        poll_timeout_seconds=_int_env("TELEGRAM_BOT_POLL_TIMEOUT_SECONDS", "10", logger),
        api_base_url=os.getenv("TELEGRAM_BOT_API_BASE_URL", "https://api.telegram.org"),
    )


def _required_env(name: str, logger: logging.Logger) -> str:
    value = os.getenv(name)
    if value and value.strip():
        return value.strip()
    logger.error("%s must be set", name)
    sys.exit(1)


def _int_env(name: str, default: str, logger: logging.Logger) -> int:
    raw_value = os.getenv(name, default)
    try:
        return int(str(raw_value).strip())
    except ValueError:
        logger.error("%s must be an integer", name)
        sys.exit(1)


def _allowed_user_ids(logger: logging.Logger) -> list[int]:
    raw_value = _required_env("TELEGRAM_BOT_ALLOWED_USER_IDS", logger)
    user_ids: list[int] = []
    for item in raw_value.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            user_ids.append(int(normalized))
        except ValueError:
            logger.error("TELEGRAM_BOT_ALLOWED_USER_IDS must contain integers only")
            sys.exit(1)
    if user_ids:
        return user_ids
    logger.error("TELEGRAM_BOT_ALLOWED_USER_IDS must not be empty")
    sys.exit(1)
