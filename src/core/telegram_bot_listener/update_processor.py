from __future__ import annotations

import logging

from core.telegram_bot_listener.bot_api import TelegramBotApi
from core.telegram_bot_listener.event_forwarder import TelegramBotEventForwarder
from core.telegram_bot_listener.json_types import JsonDict, cast_json_dict, optional_text, parse_int
from core.telegram_bot_listener.state_store import TelegramBotStateStore

logger = logging.getLogger(__name__)
_DONE_COMMAND = "/done"


class TelegramBotUpdateProcessor:
    def __init__(
        self,
        *,
        bot_api: TelegramBotApi,
        event_forwarder: TelegramBotEventForwarder,
        store: TelegramBotStateStore,
        allowed_user_ids: frozenset[int],
        poll_timeout_seconds: int,
    ) -> None:
        self._bot_api = bot_api
        self._event_forwarder = event_forwarder
        self._store = store
        self._allowed_user_ids = allowed_user_ids
        self._poll_timeout_seconds = poll_timeout_seconds

    async def run_forever(self) -> None:
        while True:
            offset = await self._next_offset()
            updates = await self._bot_api.get_updates(
                offset=offset,
                timeout_seconds=self._poll_timeout_seconds,
            )
            await _process_updates(self, updates)

    async def process_update(self, update: JsonDict) -> None:
        update_id = parse_int(update.get("update_id", 0) or 0)
        if update_id:
            await self._store.set_last_update_id(update_id)
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            await self._process_callback_query(callback_query)
            return
        message = update.get("message")
        if isinstance(message, dict):
            await self._process_message(message)

    async def _next_offset(self) -> int:
        return (await self._store.last_update_id()) + 1

    async def _process_message(self, message: JsonDict) -> None:
        chat = cast_json_dict(message.get("chat"))
        if not _is_private_chat(chat):
            return
        telegram_user_id = _extract_user_id(message.get("from"))
        if telegram_user_id is None or telegram_user_id not in self._allowed_user_ids:
            return
        chat_id = parse_int(chat.get("id"))
        text = optional_text(message.get("text"))
        if text is None:
            return
        if text == _DONE_COMMAND:
            session = await self._store.finish_active_session(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                command_text=text,
            )
            if session is not None:
                await self._event_forwarder.publish_survey_finished(session)
            return
        await self._store.record_text_message(
            telegram_user_id=telegram_user_id,
            chat_id=chat_id,
            text=text,
            kind="text",
        )

    async def _process_callback_query(self, callback_query: JsonDict) -> None:  # noqa: WPS210 - Telegram callback payload has several required fields.
        telegram_user_id = _extract_user_id(callback_query.get("from"))
        message = cast_json_dict(callback_query.get("message"))
        if not message:
            return
        if telegram_user_id is None or telegram_user_id not in self._allowed_user_ids:
            return
        chat = cast_json_dict(message.get("chat"))
        if not _is_private_chat(chat):
            return
        callback_data = optional_text(callback_query.get("data"))
        callback_id = optional_text(callback_query.get("id"))
        if callback_data is None or callback_id is None:
            return
        result = await self._store.record_selection(
            telegram_user_id=telegram_user_id,
            chat_id=parse_int(chat.get("id")),
            callback_data=callback_data,
        )
        await self._answer_callback(callback_id, result)

    async def _answer_callback(self, callback_query_id: str, result: object) -> None:
        text = "Selection saved"
        if result is None:
            text = "Unknown or inactive survey button"
        await self._bot_api.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text,
        )


def _is_private_chat(raw_chat: JsonDict) -> bool:
    return str(raw_chat.get("type")) == "private"


def _extract_user_id(raw_user: object) -> int | None:
    if not isinstance(raw_user, dict):
        return None
    user_id = raw_user.get("id")
    if isinstance(user_id, int):
        return user_id
    return None


async def _process_updates(  # noqa: WPS476 - Telegram updates must be applied sequentially.
    processor: TelegramBotUpdateProcessor,
    updates: list[JsonDict],
) -> None:
    for update in updates:
        await processor.process_update(update)  # noqa: WPS476 - Telegram update order must be preserved.
