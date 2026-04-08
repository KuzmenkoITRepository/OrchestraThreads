import logging
import os
import sys
from typing import Any

from core.telegram_events.service import TelegramEventsService

_ENV_TELEGRAM_API_ID = "TELEGRAM_API_ID"
_ENV_TELEGRAM_API_HASH = "TELEGRAM_API_HASH"
_ENV_TELEGRAM_SESSION_STRING = "TELEGRAM_SESSION_STRING"
_ENV_TELEGRAM_SESSION_FILE = "TELEGRAM_SESSION_FILE"
_ENV_EVENTS_ENGINE_URL = "EVENTS_ENGINE_URL"
_ENV_TARGET_AGENT_SLUG = "TARGET_AGENT_SLUG"
_ENV_HTTP_HOST = "TELEGRAM_EVENTS_HTTP_HOST"
_ENV_HTTP_PORT = "TELEGRAM_EVENTS_HTTP_PORT"

_DEFAULT_EVENTS_ENGINE_URL = "http://events-engine:8789"
_DEFAULT_TARGET_AGENT_SLUG = "secretary"
_DEFAULT_HTTP_HOST = "0.0.0.0"
_DEFAULT_HTTP_PORT = "8787"


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _read_required_env(name: str, logger: logging.Logger) -> str:
    env_value = os.getenv(name)
    if env_value:
        return env_value
    logger.error("%s must be set", name)
    sys.exit(1)


def _read_api_id(logger: logging.Logger) -> int:
    raw_api_id = _read_required_env(_ENV_TELEGRAM_API_ID, logger)
    try:
        return int(raw_api_id)
    except ValueError:
        logger.error("%s must be a valid integer", _ENV_TELEGRAM_API_ID)
        sys.exit(1)


def _service_options(logger: logging.Logger) -> dict[str, Any]:
    return {
        "api_id": _read_api_id(logger),
        "api_hash": _read_required_env(_ENV_TELEGRAM_API_HASH, logger),
        "session_string": os.getenv(_ENV_TELEGRAM_SESSION_STRING) or None,
        "session_file": os.getenv(_ENV_TELEGRAM_SESSION_FILE) or None,
        "events_engine_url": os.getenv(_ENV_EVENTS_ENGINE_URL, _DEFAULT_EVENTS_ENGINE_URL),
        "target_agent_slug": os.getenv(_ENV_TARGET_AGENT_SLUG, _DEFAULT_TARGET_AGENT_SLUG),
        "http_host": os.getenv(_ENV_HTTP_HOST, _DEFAULT_HTTP_HOST),
        "http_port": int(os.getenv(_ENV_HTTP_PORT, _DEFAULT_HTTP_PORT)),
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
