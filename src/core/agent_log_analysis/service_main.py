"""CLI entrypoint for the agent log analysis service."""

from __future__ import annotations

import asyncio
import logging
import os

from core.agent_log_analysis.service import run_service


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
