"""HTTP-based Telegram client that proxies to telegram-events service."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 30.0


class TelegramHTTPClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(timeout=_SEND_TIMEOUT)
        logger.info("Telegram HTTP client initialized: %s", self._base_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        error = _validate_send_inputs(chat_id, text)
        if error:
            return {"ok": False, "message_id": 0, "error": error}
        return await self._post_send(chat_id, text)

    async def _post_send(self, chat_id: int, text: str) -> dict[str, Any]:
        client = self._client
        if client is None:
            return {"ok": False, "message_id": 0, "error": "HTTP client not started"}
        url = f"{self._base_url}/send"
        try:
            response = await client.post(url, json={"chat_id": chat_id, "message": text})
        except Exception as exc:
            logger.error("HTTP request to telegram-events failed: %s", exc)
            return {"ok": False, "message_id": 0, "error": str(exc)}
        return _parse_response(response)


def _validate_send_inputs(chat_id: int, text: str) -> str | None:
    if not isinstance(chat_id, int):
        return "chat_id must be an integer"
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if len(text) > 4096:
        return "text must be 4096 characters or fewer"
    return None


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        return {
            "ok": False,
            "message_id": 0,
            "error": f"HTTP {response.status_code}: {response.text}",
        }
    if response.status_code == 200:
        return {
            "ok": bool(data.get("ok")),
            "message_id": int(data.get("message_id", 0)),
            "error": str(data.get("error", "")),
        }
    return {
        "ok": False,
        "message_id": 0,
        "error": str(data.get("error", f"HTTP {response.status_code}")),
    }
