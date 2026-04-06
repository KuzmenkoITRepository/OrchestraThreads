from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web

from core.orchestra_thread.common import ServiceError

JsonDict = dict[str, Any]
JsonDictOrNone = JsonDict | None
STATIC_DIR = Path(__file__).with_name("static")


def json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


def json_success(payload: dict[str, Any]) -> web.Response:
    return web.json_response(payload)


def service_error_response(exc: ServiceError) -> web.Response:
    return json_error(exc.message, status=exc.status)


def message_preview(text: str, *, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."
