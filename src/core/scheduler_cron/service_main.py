from __future__ import annotations

import asyncio
import logging
import os
from importlib import import_module


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    runtime_module = import_module("core.scheduler_cron.service_runtime")
    run_service = runtime_module.run_service
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
