from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_session(session_string: str | None, session_file: str | None) -> str | Any:
    if session_string:
        from telethon.sessions import StringSession

        logger.info("Using session string from environment")
        return StringSession(session_string)
    if session_file:
        logger.info("Using session file: %s", session_file)
        return session_file
    default_path = "sessions/telegram.session"
    Path("sessions").mkdir(exist_ok=True)
    logger.info("Using default session file: %s", default_path)
    return default_path
