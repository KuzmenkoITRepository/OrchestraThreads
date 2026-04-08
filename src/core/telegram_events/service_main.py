import asyncio
import logging
import signal
import sys
from collections.abc import Callable
from functools import partial

from core.telegram_events.service import TelegramEventsService
from core.telegram_events.service_config import build_service, configure_logging

_TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGINT)


def _on_signal(
    signal_number: int,
    logger: logging.Logger,
    service: TelegramEventsService,
    loop: asyncio.AbstractEventLoop,
) -> None:
    logger.info("Received signal %s, shutting down...", signal_number)
    asyncio.create_task(service.stop())
    loop.stop()


def _register_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    handler: Callable[[int], None],
) -> None:
    for signal_value in _TERMINATION_SIGNALS:
        loop.add_signal_handler(signal_value, handler, int(signal_value))


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    service = build_service(logger)
    loop = asyncio.get_running_loop()
    signal_handler = partial(_on_signal, logger=logger, service=service, loop=loop)
    _register_signal_handlers(loop, signal_handler)
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as exc:
        logger.error("Service error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
