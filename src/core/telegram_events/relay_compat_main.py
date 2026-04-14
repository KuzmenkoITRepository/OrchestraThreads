from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable
from functools import partial

from core.telegram_events.relay_compat_config import build_relay_compat_config
from core.telegram_events.relay_compat_service import TelegramRelayCompatService
from core.telegram_events.service_config import configure_logging
from core.telegram_events.service_logging import logger

_TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGINT)


def _on_signal(
    signal_number: int,
    service: TelegramRelayCompatService,
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
    service = TelegramRelayCompatService(build_relay_compat_config())
    loop = asyncio.get_running_loop()
    signal_handler = partial(_on_signal, service=service, loop=loop)
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
