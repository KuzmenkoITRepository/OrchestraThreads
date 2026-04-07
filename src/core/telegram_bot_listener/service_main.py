from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Callable
from functools import partial

from core.telegram_bot_listener.service import TelegramBotListenerService
from core.telegram_bot_listener.service_config import build_service, configure_logging


def _on_signal(
    sig: int,
    logger: logging.Logger,
    service: TelegramBotListenerService,
    loop: asyncio.AbstractEventLoop,
) -> None:
    logger.info("Received signal %s, shutting down...", sig)
    asyncio.create_task(service.stop())
    loop.stop()


def _register_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    handler: Callable[[int], None],
) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handler, int(sig))


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    service = build_service(logger)
    loop = asyncio.get_running_loop()
    signal_handler = partial(_on_signal, logger=logger, service=service, loop=loop)
    _register_signal_handlers(loop, signal_handler)
    try:
        await _serve(service)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as exc:
        logger.error("Service error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())


async def _serve(service: TelegramBotListenerService) -> None:
    await service.start()
    await asyncio.Event().wait()
