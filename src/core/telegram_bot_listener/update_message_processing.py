from __future__ import annotations

from core.telegram_bot_listener.event_forwarder import TelegramBotEventForwarder
from core.telegram_bot_listener.json_types import JsonDict, cast_json_dict, optional_text, parse_int
from core.telegram_bot_listener.state_store import TelegramBotStateStore
from core.telegram_bot_listener.update_filters import extract_user_id, is_private_chat
from core.telegram_bot_listener.update_state_interactions import (
    finish_done_command,
    record_text_message,
)

_DONE_COMMAND = "/done"


async def process_message(
    message: JsonDict,
    *,
    store: TelegramBotStateStore,
    event_forwarder: TelegramBotEventForwarder,
    allowed_user_ids: frozenset[int],
) -> None:
    chat = cast_json_dict(message.get("chat"))
    if not is_private_chat(chat):
        return
    telegram_user_id = extract_user_id(message.get("from"))
    if telegram_user_id is None or telegram_user_id not in allowed_user_ids:
        return
    text = optional_text(message.get("text"))
    if text is None:
        return
    chat_id = parse_int(chat.get("id"))
    if text == _DONE_COMMAND:
        await finish_done_command(
            store=store,
            event_forwarder=event_forwarder,
            telegram_user_id=telegram_user_id,
            chat_id=chat_id,
            command_text=text,
        )
        return
    await record_text_message(
        store=store,
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        text=text,
    )
