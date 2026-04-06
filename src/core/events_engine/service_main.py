"""Events engine service entrypoint."""

import asyncio
import logging
import os
import signal
import sys
from collections.abc import Callable
from functools import partial

from core.events_engine.service import EventsEngine


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _build_signal_handler(
    logger: logging.Logger,
    engine: EventsEngine,
    loop: asyncio.AbstractEventLoop,
) -> Callable[[int], None]:
    return partial(_on_signal, logger=logger, engine=engine, loop=loop)


def _on_signal(
    sig: int,
    logger: logging.Logger,
    engine: EventsEngine,
    loop: asyncio.AbstractEventLoop,
) -> None:
    logger.info("Received signal %s, shutting down...", sig)
    asyncio.create_task(engine.stop())
    loop.stop()


def _register_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    signal_handler: Callable[[int], None],
) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler, int(sig))


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    orchestra_agents_url = os.getenv("ORCHESTRA_AGENTS_URL", "http://orchestra-agents:8790")

    engine = EventsEngine(orchestra_agents_url=orchestra_agents_url)
    loop = asyncio.get_running_loop()
    _register_signal_handlers(loop, _build_signal_handler(logger, engine, loop))

    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as exc:
        logger.error("Service error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
