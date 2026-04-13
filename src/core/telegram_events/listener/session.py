from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def build_session(session_string: str | None, session_file: str | None) -> str | Any:
    if session_string:
        _, telethon_sessions = load_telethon()

        logger.info("Using session string from environment")
        return cast(Any, telethon_sessions).StringSession(session_string)
    if session_file:
        logger.info("Using session file: %s", session_file)
        return session_file
    default_path = "sessions/telegram.session"
    Path("sessions").mkdir(exist_ok=True)
    logger.info("Using default session file: %s", default_path)
    return default_path


def load_telethon() -> tuple[type[Any], Any]:
    telethon_module = import_module("telethon")
    telegram_client = telethon_module.TelegramClient
    sessions = telethon_module.sessions

    return cast(type[Any], telegram_client), sessions
