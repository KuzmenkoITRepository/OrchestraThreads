from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from core.telegram_events import service_config


class ServiceConfigTests(unittest.TestCase):
    def test_build_service_passes_mcp_url(self) -> None:
        service = self._build_service(
            {
                "BETTER_TELEGRAM_MCP_URL": "http://example.test/mcp",
                "BETTER_TELEGRAM_MCP_EVENTS_URL": "http://example.test/events",
                "BETTER_TELEGRAM_MCP_TOKEN": "secret-token",
            }
        )

        service.assert_called_once()
        self.assertEqual(service.call_args.kwargs["mcp_url"], "http://example.test/mcp")

    def test_build_service_passes_events_url(self) -> None:
        service = self._build_service(
            {
                "BETTER_TELEGRAM_MCP_URL": "http://example.test/mcp",
                "BETTER_TELEGRAM_MCP_EVENTS_URL": "http://example.test/events",
                "BETTER_TELEGRAM_MCP_TOKEN": "secret-token",
            }
        )

        service.assert_called_once()
        self.assertEqual(service.call_args.kwargs["events_url"], "http://example.test/events")

    def test_build_service_passes_bearer_token(self) -> None:
        service = self._build_service(
            {
                "BETTER_TELEGRAM_MCP_URL": "http://example.test/mcp",
                "BETTER_TELEGRAM_MCP_EVENTS_URL": "http://example.test/events",
                "BETTER_TELEGRAM_MCP_TOKEN": "secret-token",
            }
        )

        service.assert_called_once()
        self.assertEqual(service.call_args.kwargs["bearer_token"], "secret-token")

    def test_build_service_passes_threads_url(self) -> None:
        service = self._build_service(
            {
                "BETTER_TELEGRAM_MCP_TOKEN": "secret-token",
                "ORCHESTRA_THREADS_URL": "http://threads.test:8788",
            }
        )

        service.assert_called_once()
        self.assertEqual(service.call_args.kwargs["threads_url"], "http://threads.test:8788")

    def test_build_service_passes_agent_slug(self) -> None:
        service = self._build_service(
            {
                "BETTER_TELEGRAM_MCP_TOKEN": "secret-token",
                "TELEGRAM_EVENTS_AGENT_SLUG": "telegram_gateway",
            }
        )

        service.assert_called_once()
        self.assertEqual(service.call_args.kwargs["agent_slug"], "telegram_gateway")

    def test_build_service_passes_public_base_url(self) -> None:
        service = self._build_service(
            {
                "BETTER_TELEGRAM_MCP_TOKEN": "secret-token",
                "TELEGRAM_EVENTS_PUBLIC_BASE_URL": "http://telegram-events:8787",
            }
        )

        service.assert_called_once()
        self.assertEqual(
            service.call_args.kwargs["public_base_url"],
            "http://telegram-events:8787",
        )

    def _build_service(self, env: dict[str, str]) -> MagicMock:
        logger = logging.getLogger("test_service_config")
        with patch.dict(os.environ, env, clear=False):
            with patch.object(service_config, "TelegramEventsService") as mock_service:
                service_config.build_service(logger)
                return mock_service


if __name__ == "__main__":
    unittest.main()
