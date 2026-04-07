from __future__ import annotations

import logging

import httpx

from core.telegram_bot_listener.json_types import JsonDict, cast_json_dict

logger = logging.getLogger(__name__)


class TelegramBotApi:
    def __init__(
        self,
        *,
        bot_token: str,
        api_base_url: str,
        timeout_seconds: float,
    ) -> None:
        self._base_url = f"{api_base_url.rstrip('/')}/bot{bot_token}"
        self._client = httpx.AsyncClient(timeout=timeout_seconds, trust_env=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_updates(self, *, offset: int, timeout_seconds: int) -> list[JsonDict]:
        payload = await self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout_seconds,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        result = payload.get("result")
        if isinstance(result, list):
            return [cast_json_dict(item) for item in result if isinstance(item, dict)]
        return []

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: JsonDict | None = None,
    ) -> JsonDict:
        payload: JsonDict = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def answer_callback_query(self, *, callback_query_id: str, text: str) -> JsonDict:
        return await self._call(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text},
        )

    async def _call(self, method: str, payload: JsonDict) -> JsonDict:
        response = await self._client.post(f"{self._base_url}/{method}", json=payload)
        response.raise_for_status()
        raw_payload = cast_json_dict(response.json())
        if raw_payload.get("ok") is not True:
            raise RuntimeError(
                str(raw_payload.get("description") or f"Telegram API call failed: {method}")
            )
        return raw_payload


def extract_message_id(payload: JsonDict) -> int:
    result = payload.get("result")
    if isinstance(result, dict):
        message_id = result.get("message_id")
        if isinstance(message_id, int):
            return message_id
    raise RuntimeError("Telegram API response did not contain message_id")


def build_inline_keyboard(buttons: list[list[JsonDict]]) -> JsonDict:
    return {"inline_keyboard": [[dict(button) for button in row] for row in buttons]}
