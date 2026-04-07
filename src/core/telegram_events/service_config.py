import logging
import os
import sys
from typing import Any

from core.telegram_events.service import TelegramEventsService


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _read_required_env(name: str, logger: logging.Logger) -> str:
    value = os.getenv(name)
    if value:
        return value
    logger.error("%s must be set", name)
    sys.exit(1)


def _read_api_id(logger: logging.Logger) -> int:
    raw_api_id = _read_required_env("TELEGRAM_API_ID", logger)
    try:
        return int(raw_api_id)
    except ValueError:
        logger.error("TELEGRAM_API_ID must be a valid integer")
        sys.exit(1)


def _service_options(logger: logging.Logger) -> dict[str, Any]:
    return {
        "api_id": _read_api_id(logger),
        "api_hash": _read_required_env("TELEGRAM_API_HASH", logger),
        "session_string": os.getenv("TELEGRAM_SESSION_STRING") or None,
        "session_file": os.getenv("TELEGRAM_SESSION_FILE") or None,
        "events_engine_url": os.getenv("EVENTS_ENGINE_URL", "http://events-engine:8789"),
        "target_agent_slug": os.getenv("TARGET_AGENT_SLUG", "secretary"),
        "http_host": os.getenv("TELEGRAM_EVENTS_HTTP_HOST", "0.0.0.0"),
        "http_port": int(os.getenv("TELEGRAM_EVENTS_HTTP_PORT", "8787")),
    }


def build_service(logger: logging.Logger) -> TelegramEventsService:
    service_options = _service_options(logger)
    return TelegramEventsService(
        api_id=service_options["api_id"],
        api_hash=service_options["api_hash"],
        session_string=service_options["session_string"],
        session_file=service_options["session_file"],
        events_engine_url=service_options["events_engine_url"],
        target_agent_slug=service_options["target_agent_slug"],
        http_host=service_options["http_host"],
        http_port=service_options["http_port"],
    )
