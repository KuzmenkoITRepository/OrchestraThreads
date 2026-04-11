from __future__ import annotations

from core.telegram_bot_listener.bot_api import TelegramBotApi
from core.telegram_bot_listener.json_types import JsonDict, cast_json_dict, optional_text, parse_int
from core.telegram_bot_listener.models import SelectionResult
from core.telegram_bot_listener.state_store import TelegramBotStateStore
from core.telegram_bot_listener.update_filters import extract_user_id, is_private_chat
from core.telegram_bot_listener.update_state_interactions import record_selection


async def process_callback_query(
    callback_query: JsonDict,
    *,
    bot_api: TelegramBotApi,
    store: TelegramBotStateStore,
    allowed_user_ids: frozenset[int],
) -> None:
    telegram_user_id = extract_user_id(callback_query.get("from"))
    message = cast_json_dict(callback_query.get("message"))
    callback_identity = _callback_identity(callback_query)
    if not message or callback_identity is None:
        return
    if telegram_user_id is None or telegram_user_id not in allowed_user_ids:
        return
    chat = cast_json_dict(message.get("chat"))
    if not is_private_chat(chat):
        return
    result = await record_selection(
        store=store,
        telegram_user_id=telegram_user_id,
        chat_id=parse_int(chat.get("id")),
        callback_data=callback_identity.data,
    )
    await answer_callback(
        bot_api=bot_api,
        callback_query_id=callback_identity.callback_id,
        result=result,
    )


async def answer_callback(
    *,
    bot_api: TelegramBotApi,
    callback_query_id: str,
    result: SelectionResult | None,
) -> None:
    text = "Selection saved"
    if result is None:
        text = "Unknown or inactive survey button"
    await bot_api.answer_callback_query(callback_query_id=callback_query_id, text=text)


class _CallbackIdentity:
    def __init__(self, callback_id: str, data: str) -> None:
        self.callback_id = callback_id
        self.data = data


def _callback_identity(callback_query: JsonDict) -> _CallbackIdentity | None:
    callback_data = optional_text(callback_query.get("data"))
    callback_id = optional_text(callback_query.get("id"))
    if callback_data is None or callback_id is None:
        return None
    return _CallbackIdentity(callback_id=callback_id, data=callback_data)
