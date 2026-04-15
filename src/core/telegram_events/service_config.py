import logging
import os
import sys
from typing import Any

from core.telegram_events.service import TelegramEventsService

_ENV_BETTER_TELEGRAM_MCP_TOKEN = "BETTER_TELEGRAM_MCP_TOKEN"
_ENV_EVENTS_ENGINE_URL = "EVENTS_ENGINE_URL"
_ENV_HTTP_HOST = "TELEGRAM_EVENTS_HTTP_HOST"
_ENV_HTTP_PORT = "TELEGRAM_EVENTS_HTTP_PORT"
_ENV_ORCHESTRA_THREADS_URL = "ORCHESTRA_THREADS_URL"

_DEFAULT_EVENTS_ENGINE_URL = "http://events-engine:8789"
_DEFAULT_HTTP_HOST = "0.0.0.0"
_DEFAULT_HTTP_PORT = "8787"
_DEFAULT_ORCHESTRA_THREADS_URL = "http://orchestra-threads:8788"


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


def _service_options(logger: logging.Logger) -> dict[str, Any]:
    return {
        "bearer_token": _read_required_env(_ENV_BETTER_TELEGRAM_MCP_TOKEN, logger),
        "events_engine_url": os.getenv(_ENV_EVENTS_ENGINE_URL, _DEFAULT_EVENTS_ENGINE_URL),
        "http_host": os.getenv(_ENV_HTTP_HOST, _DEFAULT_HTTP_HOST),
        "http_port": int(os.getenv(_ENV_HTTP_PORT, _DEFAULT_HTTP_PORT)),
        "threads_url": os.getenv(_ENV_ORCHESTRA_THREADS_URL, _DEFAULT_ORCHESTRA_THREADS_URL),
    }


def build_service(logger: logging.Logger) -> TelegramEventsService:
    service_options = _service_options(logger)
    return TelegramEventsService(
        bearer_token=service_options["bearer_token"],
        events_engine_url=service_options["events_engine_url"],
        http_host=service_options["http_host"],
        http_port=service_options["http_port"],
        threads_url=service_options["threads_url"],
    )
