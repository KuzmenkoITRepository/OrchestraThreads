from __future__ import annotations

from core.telegram_bot_listener.event_forwarder import TelegramBotEventForwarder
from core.telegram_bot_listener.json_types import JsonDict, parse_int
from core.telegram_bot_listener.models import SelectionResult
from core.telegram_bot_listener.state_store import TelegramBotStateStore


async def mark_processed_update(store: TelegramBotStateStore, update: JsonDict) -> None:
    update_id = parse_int(update.get("update_id", 0) or 0)
    if update_id:
        await store.set_last_update_id(update_id)


async def finish_done_command(
    *,
    store: TelegramBotStateStore,
    event_forwarder: TelegramBotEventForwarder,
    telegram_user_id: int,
    chat_id: int,
    command_text: str,
) -> None:
    session = await store.finish_active_session(
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        command_text=command_text,
    )
    if session is not None:
        await event_forwarder.publish_survey_finished(session)


async def record_text_message(
    *,
    store: TelegramBotStateStore,
    telegram_user_id: int,
    chat_id: int,
    text: str,
) -> None:
    await store.record_text_message(
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        text=text,
        kind="text",
    )


async def record_selection(
    *,
    store: TelegramBotStateStore,
    telegram_user_id: int,
    chat_id: int,
    callback_data: str,
) -> SelectionResult | None:
    return await store.record_selection(
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        callback_data=callback_data,
    )
