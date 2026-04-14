from __future__ import annotations

import asyncio
import logging
import typing
from collections import deque

from aiohttp import web

from core.telegram_events import (
    relay_compat_config,
    relay_compat_lifecycle,
    relay_compat_rpc,
)
from core.telegram_events.listener import runtime as listener_runtime
from core.telegram_events.service import support as service_support

logger = logging.getLogger(__name__)

_QUEUE_MAX_SIZE = 100
_RECENT_EVENT_LIMIT = 50


class _RelayListener(typing.Protocol):
    client: object | None

    async def start_client(self) -> object: ...

    async def stop(self) -> None: ...


class TelegramRelayCompatService:
    def __init__(
        self,
        config: relay_compat_config.RelayCompatConfig,
        listener: _RelayListener | None = None,
    ) -> None:
        self._config = config
        self._listener = listener or listener_runtime.TelegramListener(
            api_id=config.api_id,
            api_hash=config.api_hash,
            session_string=config.session_string,
            session_file=config.session_file,
            on_message=self._handle_message,
        )
        self._http_runner: web.AppRunner | None = None
        self._shutdown_event = asyncio.Event()
        self._subscribers: set[asyncio.Queue[str | None]] = set()
        self._recent_events: deque[str] = deque(maxlen=_RECENT_EVENT_LIMIT)
        self._rpc_handler = relay_compat_rpc.RelayCompatRpcHandler(
            config.recipient_chat_ids,
            self._listener,
        )

    async def start(self) -> None:
        logger.info("Starting better-telegram-mcp compatibility service...")
        service_support.clear_proxy_env()
        await self._listener.start_client()
        self._http_runner = await relay_compat_lifecycle.start_http_server(
            self,
            self._config.bearer_token,
            self._config.host,
            self._config.port,
        )
        logger.info(
            "Telegram relay compatibility service listening on %s:%s",
            self._config.host,
            self._config.port,
        )
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        self._shutdown_event.set()
        await relay_compat_lifecycle.close_subscribers(self._subscribers)
        if self._http_runner is not None:
            await self._http_runner.cleanup()
            self._http_runner = None
        await self._listener.stop()

    def subscribe(self) -> asyncio.Queue[str | None]:
        subscriber: asyncio.Queue[str | None] = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
        for payload in self._recent_events:
            subscriber.put_nowait(payload)
        self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: asyncio.Queue[str | None]) -> None:
        self._subscribers.discard(subscriber)

    async def handle_json_rpc(self, payload: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return await self._rpc_handler.handle(payload)

    async def _handle_message(self, message_data: dict[str, typing.Any]) -> None:
        payload = relay_compat_lifecycle.serialize_message_payload(message_data)
        self._recent_events.append(payload)
        await relay_compat_lifecycle.broadcast_payload(self._subscribers, payload)
