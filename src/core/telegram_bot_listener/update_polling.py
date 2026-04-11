from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.telegram_bot_listener.bot_api import TelegramBotApi
from core.telegram_bot_listener.json_types import JsonDict
from core.telegram_bot_listener.state_store import TelegramBotStateStore


async def run_forever(
    process_update: Callable[[JsonDict], Awaitable[None]],
    *,
    bot_api: TelegramBotApi,
    store: TelegramBotStateStore,
    poll_timeout_seconds: int,
) -> None:
    while True:
        updates = await bot_api.get_updates(
            offset=await next_offset(store),
            timeout_seconds=poll_timeout_seconds,
        )
        await process_updates(process_update, updates)


async def next_offset(store: TelegramBotStateStore) -> int:
    return (await store.last_update_id()) + 1


async def process_updates(
    process_update: Callable[[JsonDict], Awaitable[None]],
    updates: list[JsonDict],
) -> None:
    for update in updates:
        await process_update(update)  # noqa: WPS476 - Telegram update order must be preserved.
