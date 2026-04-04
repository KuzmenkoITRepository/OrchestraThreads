"""Events engine service entrypoint."""

import asyncio
import logging
import os
import signal
import sys

from .service import EventsEngine


def configure_logging():
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main():
    configure_logging()
    logger = logging.getLogger(__name__)

    orchestra_agents_url = os.getenv(
        "ORCHESTRA_AGENTS_URL", "http://orchestra-agents:8790"
    )

    engine = EventsEngine(orchestra_agents_url=orchestra_agents_url)

    loop = asyncio.get_event_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(engine.stop())
        loop.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
