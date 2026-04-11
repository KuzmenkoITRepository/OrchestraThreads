from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiohttp import web

from core.telegram_bot_listener.bot_api import TelegramBotApi
from core.telegram_bot_listener.event_forwarder import TelegramBotEventForwarder
from core.telegram_bot_listener.service_app import build_app, service_site
from core.telegram_bot_listener.state_store import TelegramBotStateStore
from core.telegram_bot_listener.update_processor import TelegramBotUpdateProcessor

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramBotListenerConfig:
    host: str
    port: int
    bot_token: str
    allowed_user_ids: frozenset[int]
    api_token: str
    events_engine_url: str
    target_agent_slug: str
    state_file: str
    poll_timeout_seconds: int
    api_base_url: str


class TelegramBotListenerService:
    def __init__(self, config: TelegramBotListenerConfig) -> None:
        self.config = config
        self.store = TelegramBotStateStore(config.state_file)
        self.bot_api = TelegramBotApi(
            bot_token=config.bot_token,
            api_base_url=config.api_base_url,
            timeout_seconds=max(5.0, float(config.poll_timeout_seconds + 5)),
        )
        self._forwarder = TelegramBotEventForwarder(
            events_engine_url=config.events_engine_url,
            target_agent_slug=config.target_agent_slug,
        )
        self._processor = TelegramBotUpdateProcessor(
            bot_api=self.bot_api,
            event_forwarder=self._forwarder,
            store=self.store,
            allowed_user_ids=config.allowed_user_ids,
            poll_timeout_seconds=config.poll_timeout_seconds,
        )
        self._runner: web.AppRunner | None = None
        self._polling_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._runner is not None:
            return
        await self.store.start()
        self._runner = web.AppRunner(build_app(self))
        await self._runner.setup()
        await service_site(self).start()
        self._polling_task = asyncio.create_task(self._processor.run_forever())
        logger.info(
            "telegram_bot_listener listening on %s:%s",
            self.config.host,
            self.config.port,
        )

    async def stop(self) -> None:
        polling_task = self._polling_task
        if polling_task is not None:
            polling_task.cancel()
            await asyncio.gather(polling_task, return_exceptions=True)
            self._polling_task = None
        runner = self._runner
        if runner is not None:
            self._runner = None
            await runner.cleanup()
        await self._forwarder.close()
        await self.bot_api.close()
        await self.store.close()

    async def is_healthy(self) -> bool:
        polling_task = self._polling_task
        if polling_task is None:
            return False
        return not polling_task.done()
