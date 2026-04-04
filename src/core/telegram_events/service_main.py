"""Telegram events service entrypoint."""

import asyncio
import logging
import os
import signal
import sys

from .service import TelegramEventsService


def configure_logging():
    """Configure logging for the service."""
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main():
    configure_logging()
    logger = logging.getLogger(__name__)

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session_string = os.getenv("TELEGRAM_SESSION_STRING")
    session_file = os.getenv("TELEGRAM_SESSION_FILE")
    events_engine_url = os.getenv("EVENTS_ENGINE_URL", "http://events-engine:8789")
    target_agent_slug = os.getenv("TARGET_AGENT_SLUG", "secretary")

    if not api_id or not api_hash:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")
        sys.exit(1)

    try:
        api_id = int(api_id)
    except ValueError:
        logger.error("TELEGRAM_API_ID must be a valid integer")
        sys.exit(1)

    service = TelegramEventsService(
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string or None,
        session_file=session_file or None,
        events_engine_url=events_engine_url,
        target_agent_slug=target_agent_slug,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(service.stop())
        loop.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # Start service
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
