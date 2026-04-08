"""HTTP-based Telegram client that proxies sends to telegram-events."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 30.0
_MAX_MESSAGE_LENGTH = 4096


class TelegramHTTPClient:
    """Thin HTTP proxy: delegates send_message to telegram-events /send."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize the underlying httpx client."""
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            timeout=_SEND_TIMEOUT,
            trust_env=False,
        )
        logger.info("Telegram HTTP client ready: %s", self._base_url)

    async def close(self) -> None:
        """Shut down the httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_message(
        self,
        chat_id: int,
        text: str,
    ) -> dict[str, Any]:
        """Send a message via telegram-events /send endpoint."""
        error = _validate_send_inputs(chat_id, text)
        if error:
            return {"ok": False, "message_id": 0, "error": error}
        return await self._post_send(chat_id, text)

    async def _post_send(
        self,
        chat_id: int,
        text: str,
    ) -> dict[str, Any]:
        client = self._client
        if client is None:
            return {"ok": False, "message_id": 0, "error": "HTTP client not started"}
        url = f"{self._base_url}/send"
        try:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "message": text},
            )
        except Exception as exc:
            logger.error("HTTP request to telegram-events failed: %s", exc)
            return {"ok": False, "message_id": 0, "error": str(exc)}
        return _parse_response(response)


def _validate_send_inputs(chat_id: int, text: str) -> str | None:
    if not isinstance(chat_id, int):
        return "chat_id must be an integer"
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if len(text) > _MAX_MESSAGE_LENGTH:
        return f"text must be {_MAX_MESSAGE_LENGTH} characters or fewer"
    return None


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    try:
        raw = response.json()
    except Exception:
        return {
            "ok": False,
            "message_id": 0,
            "error": f"HTTP {response.status_code}: {response.text}",
        }
    if not isinstance(raw, dict):
        return {"ok": False, "message_id": 0, "error": "unexpected JSON shape"}
    if response.status_code == 200:
        return _extract_success(raw)
    return {
        "ok": False,
        "message_id": 0,
        "error": str(raw.get("error", f"HTTP {response.status_code}")),
    }


def _extract_success(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        msg_id = int(raw.get("message_id", 0) or 0)
    except (TypeError, ValueError):
        msg_id = 0
    return {
        "ok": bool(raw.get("ok")),
        "message_id": msg_id,
        "error": str(raw.get("error", "")),
    }
