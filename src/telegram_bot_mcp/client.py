from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import aiohttp

ButtonRows = list[list[dict[str, str]]]


@dataclass(frozen=True)
class _RequestSpec:
    method: str
    path: str
    json_payload: dict[str, Any] | None = None


class TelegramBotListenerClient:  # noqa: WPS214 - Small HTTP wrapper mirrors the listener API surface.
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send_message(self, *, telegram_user_id: int, text: str) -> dict[str, Any]:
        return await self._request(
            _RequestSpec(
                method="POST",
                path="/api/v1/messages",
                json_payload={"telegram_user_id": telegram_user_id, "text": text},
            )
        )

    async def send_buttons(
        self,
        *,
        telegram_user_id: int,
        text: str,
        buttons: ButtonRows,
    ) -> dict[str, Any]:
        return await self._request(
            _RequestSpec(
                method="POST",
                path="/api/v1/buttons",
                json_payload={
                    "telegram_user_id": telegram_user_id,
                    "text": text,
                    "buttons": buttons,
                },
            )
        )

    async def create_survey(
        self,
        *,
        telegram_user_id: int,
        title: str,
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._request(
            _RequestSpec(
                method="POST",
                path="/api/v1/surveys",
                json_payload={
                    "telegram_user_id": telegram_user_id,
                    "title": title,
                    "questions": questions,
                },
            )
        )

    async def get_history(
        self,
        *,
        telegram_user_id: int,
        limit: int,
        session_id: str | None,
    ) -> dict[str, Any]:
        query = f"telegram_user_id={telegram_user_id}&limit={max(1, int(limit))}"
        if session_id:
            query = f"{query}&session_id={session_id}"
        return await self._request(_RequestSpec(method="GET", path=f"/api/v1/history?{query}"))

    async def _request(self, spec: _RequestSpec) -> dict[str, Any]:
        session = await self._session_or_create()
        async with session.request(
            spec.method,
            f"{self.base_url}{spec.path}",
            json=spec.json_payload,
            headers={"X-Telegram-Bot-Listener-Token": self.api_token},
        ) as response:
            raw_body = await response.text()
            payload = _parse_payload(raw_body, status=response.status)
            if response.status >= 400:
                raise RuntimeError(str(payload.get("error") or payload))
            return payload

    async def _session_or_create(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            )
        return self._session


def _parse_payload(raw_body: str, *, status: int) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(raw_body or f"HTTP {status}") from exc
    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError("Listener returned a non-object JSON response")
