from __future__ import annotations

from core.telegram_bot_listener.bot_api import TelegramBotApi
from core.telegram_bot_listener.event_forwarder import TelegramBotEventForwarder
from core.telegram_bot_listener.json_types import JsonDict
from core.telegram_bot_listener.state_store import TelegramBotStateStore
from core.telegram_bot_listener.update_callback_processing import process_callback_query
from core.telegram_bot_listener.update_message_processing import process_message
from core.telegram_bot_listener.update_polling import run_forever
from core.telegram_bot_listener.update_state_interactions import mark_processed_update


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
        await run_forever(
            self.process_update,
            bot_api=self._bot_api,
            store=self._store,
            poll_timeout_seconds=self._poll_timeout_seconds,
        )

    async def process_update(self, update: JsonDict) -> None:
        await mark_processed_update(self._store, update)
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            await process_callback_query(
                callback_query,
                bot_api=self._bot_api,
                store=self._store,
                allowed_user_ids=self._allowed_user_ids,
            )
            return
        message = update.get("message")
        if isinstance(message, dict):
            await process_message(
                message,
                store=self._store,
                event_forwarder=self._event_forwarder,
                allowed_user_ids=self._allowed_user_ids,
            )
