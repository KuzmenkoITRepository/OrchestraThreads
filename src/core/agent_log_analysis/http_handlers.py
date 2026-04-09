"""HTTP transport handlers for ingest and point lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aiohttp import web

from core.agent_log_analysis import common
from core.agent_log_analysis.errors import EventConflictError, EventNotFoundError, ValidationError


class _RuntimeProtocol(Protocol):
    async def is_healthy(self) -> bool: ...

    async def ingest_event(
        self, payload: object, *, authorization: str | None
    ) -> dict[str, Any]: ...

    async def ingest_batch(
        self, payload: object, *, authorization: str | None
    ) -> dict[str, Any]: ...

    async def get_event(self, event_id: str) -> dict[str, Any]: ...


def json_success(
    data: dict[str, Any],
    *,
    status: int = common.HTTP_OK,
) -> web.Response:
    """Return stable success envelope."""
    return web.json_response({"status": "ok", "data": data}, status=status)


def json_error(error_code: str, message: str, *, status: int) -> web.Response:
    """Return stable error envelope."""
    return web.json_response(
        {
            "status": "error",
            "error_code": error_code,
            "message": message,
        },
        status=status,
    )


@dataclass(frozen=True)
class AgentLogAnalysisHttpHandlers:
    """Transport-only request handlers."""

    runtime: _RuntimeProtocol

    async def healthz(self, _: web.Request) -> web.Response:
        if not await self.runtime.is_healthy():
            return json_error(
                common.ERROR_SERVICE_UNAVAILABLE,
                "service is unavailable",
                status=common.HTTP_UNAVAILABLE,
            )
        return web.json_response({"status": "ok"}, status=common.HTTP_OK)

    async def ingest_event(self, request: web.Request) -> web.Response:
        return await _handle_json_request(
            request,
            callback=self.runtime.ingest_event,
        )

    async def ingest_batch(self, request: web.Request) -> web.Response:
        return await _handle_json_request(
            request,
            callback=self.runtime.ingest_batch,
        )

    async def get_event(self, request: web.Request) -> web.Response:
        event_id = request.match_info.get("event_id", "").strip()
        if not event_id:
            return json_error(
                common.ERROR_VALIDATION,
                "event_id is required",
                status=common.HTTP_BAD_REQUEST,
            )
        try:
            data = await self.runtime.get_event(event_id)
        except EventNotFoundError as err:
            return json_error(
                common.ERROR_EVENT_NOT_FOUND,
                str(err),
                status=common.HTTP_NOT_FOUND,
            )
        return json_success(data)


async def _handle_json_request(
    request: web.Request,
    *,
    callback: Any,
) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return json_error(
            common.ERROR_VALIDATION,
            "request body must be valid JSON",
            status=common.HTTP_BAD_REQUEST,
        )
    authorization = request.headers.get("Authorization")
    try:
        data = await callback(payload, authorization=authorization)
    except ValidationError as err:
        return _validation_error(err)
    except EventConflictError as err:
        return json_error(
            common.ERROR_EVENT_CONFLICT,
            str(err),
            status=common.HTTP_CONFLICT,
        )
    return json_success(data)


def _validation_error(err: ValidationError) -> web.Response:
    status = common.HTTP_BAD_REQUEST
    if err.error_code in {"AUTH_REQUIRED", "AUTH_INVALID"}:
        status = common.HTTP_UNAUTHORIZED
    return json_error(err.error_code, err.message, status=status)
