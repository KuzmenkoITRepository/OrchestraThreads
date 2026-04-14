from __future__ import annotations

import os
from dataclasses import dataclass

_HOST_ENV = "HOST"
_PORT_ENV = "PORT"
_API_ID_ENV = "TELEGRAM_API_ID"
_API_HASH_ENV = "TELEGRAM_API_HASH"
_SESSION_STRING_ENV = "TELEGRAM_SESSION_STRING"
_SESSION_FILE_ENV = "TELEGRAM_SESSION_FILE"
_TOKEN_ENV = "BETTER_TELEGRAM_MCP_TOKEN"
_CHAT_ID_PREFIX = "TELEGRAM_CHAT_ID_"


@dataclass(frozen=True)
class RelayCompatConfig:
    host: str
    port: int
    bearer_token: str
    api_id: int
    api_hash: str
    session_string: str
    session_file: str | None
    recipient_chat_ids: dict[str, str]


def build_relay_compat_config() -> RelayCompatConfig:
    return RelayCompatConfig(
        host=os.getenv(_HOST_ENV, "0.0.0.0"),
        port=_read_port(),
        bearer_token=_require_env(_TOKEN_ENV),
        api_id=_read_api_id(),
        api_hash=_require_env(_API_HASH_ENV),
        session_string=_require_env(_SESSION_STRING_ENV),
        session_file=os.getenv(_SESSION_FILE_ENV),
        recipient_chat_ids=_read_recipient_chat_ids(),
    )


def _read_port() -> int:
    raw_port = os.getenv(_PORT_ENV, "3000")
    return int(raw_port)


def _read_api_id() -> int:
    return int(_require_env(_API_ID_ENV))


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    msg = f"{name} must be set"
    raise RuntimeError(msg)


def _read_recipient_chat_ids() -> dict[str, str]:
    recipient_chat_ids: dict[str, str] = {}
    for name, value in os.environ.items():
        if not name.startswith(_CHAT_ID_PREFIX) or not value:
            continue
        recipient = name.removeprefix(_CHAT_ID_PREFIX).lower()
        recipient_chat_ids[recipient] = value
    return recipient_chat_ids
