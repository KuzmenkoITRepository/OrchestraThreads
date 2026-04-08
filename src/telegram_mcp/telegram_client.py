from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEND_TIMEOUT_SECONDS = 30.0
_MAX_TEXT_LENGTH = 4096
_SEND_ENDPOINT = "/send"
_HTTP_CLIENT_NOT_STARTED = "HTTP client not started"

_KEY_OK = "ok"
_KEY_MESSAGE_ID = "message_id"
_KEY_ERROR = "error"


class TelegramHTTPClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS)
        logger.info("Telegram HTTP client initialized: %s", self._base_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        validation_error = _validate_send_inputs(chat_id, text)
        if validation_error:
            return {_KEY_OK: False, _KEY_MESSAGE_ID: 0, _KEY_ERROR: validation_error}
        return await self._post_send(chat_id, text)

    async def _post_send(self, chat_id: int, text: str) -> dict[str, Any]:
        client = self._client
        if client is None:
            return {_KEY_OK: False, _KEY_MESSAGE_ID: 0, _KEY_ERROR: _HTTP_CLIENT_NOT_STARTED}
        url = f"{self._base_url}{_SEND_ENDPOINT}"
        try:
            response = await client.post(url, json={"chat_id": chat_id, "message": text})
        except Exception as exc:
            logger.error("HTTP request to telegram-events failed: %s", exc)
            return {_KEY_OK: False, _KEY_MESSAGE_ID: 0, _KEY_ERROR: str(exc)}
        return _parse_response(response)


def _validate_send_inputs(chat_id: int, text: str) -> str | None:
    if not isinstance(chat_id, int):
        return "chat_id must be an integer"
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if len(text) > _MAX_TEXT_LENGTH:
        return f"text must be {_MAX_TEXT_LENGTH} characters or fewer"
    return None


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    try:
        response_payload = response.json()
    except Exception:
        return {
            _KEY_OK: False,
            _KEY_MESSAGE_ID: 0,
            _KEY_ERROR: f"HTTP {response.status_code}: {response.text}",
        }
    if response.status_code == 200:
        return {
            _KEY_OK: bool(response_payload.get(_KEY_OK)),
            _KEY_MESSAGE_ID: int(response_payload.get(_KEY_MESSAGE_ID, 0)),
            _KEY_ERROR: str(response_payload.get(_KEY_ERROR, "")),
        }
    return {
        _KEY_OK: False,
        _KEY_MESSAGE_ID: 0,
        _KEY_ERROR: str(response_payload.get(_KEY_ERROR, f"HTTP {response.status_code}")),
    }
