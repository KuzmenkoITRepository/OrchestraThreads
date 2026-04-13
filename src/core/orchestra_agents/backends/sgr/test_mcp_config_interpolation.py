from __future__ import annotations

import contextlib
import os
import unittest
from unittest.mock import patch

from core.orchestra_agents.backends.sgr import mcp_loader
from core.orchestra_agents.backends.sgr._mcp_config_interpolation import (
    interpolate_config_values,
)


class _EnvSwapper:
    """Context manager to temporarily set an env var."""

    def __init__(self, key: str, value: str) -> None:
        self._key = key
        self._value = value
        self._previous: str | None = None

    def __enter__(self) -> None:
        self._previous = os.environ.get(self._key)
        os.environ[self._key] = self._value

    def __exit__(self, *args: object) -> None:
        if self._previous is None:
            os.environ.pop(self._key, None)
        else:
            os.environ[self._key] = self._previous


def _swap_env(key: str, value: str) -> contextlib.AbstractContextManager[None]:
    return _EnvSwapper(key, value)


def _make_http_config(*, token: str) -> dict[str, object]:
    return {
        "mcp_servers": [
            {
                "name": "telegram_relay",
                "transport": "http",
                "url": "http://example.test/mcp",
                "bearer_token": "{env.BETTER_TELEGRAM_MCP_TOKEN}",
                "enabled_tools": ["telegram_send"],
            }
        ]
    }


class MCPConfigInterpolationTests(unittest.TestCase):
    def test_string_placeholder(self) -> None:
        with _swap_env("BETTER_TELEGRAM_MCP_URL", "http://example.test/mcp"):
            payload = interpolate_config_values({"url": "{env.BETTER_TELEGRAM_MCP_URL}"})

        self.assertEqual(payload["url"], "http://example.test/mcp")

    def test_nested_dict_values(self) -> None:
        with _swap_env("BETTER_TELEGRAM_MCP_TOKEN", "secret-token"):
            payload = interpolate_config_values(
                {
                    "server": {
                        "name": "telegram_relay",
                        "bearer_token": "{env.BETTER_TELEGRAM_MCP_TOKEN}",
                    }
                }
            )

        self.assertEqual(payload["server"]["bearer_token"], "secret-token")

    def test_list_items(self) -> None:
        with _swap_env("BETTER_TELEGRAM_MCP_URL", "http://example.test/mcp"):
            payload = interpolate_config_values(
                {
                    "servers": [
                        "{env.BETTER_TELEGRAM_MCP_URL}",
                        "static-value",
                    ]
                }
            )

        self.assertEqual(payload["servers"], ["http://example.test/mcp", "static-value"])

    def test_missing_env_raises_value_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Missing required environment variable: MISSING_BETTER_TELEGRAM_MCP_TOKEN",
        ):
            interpolate_config_values({"token": "{env.MISSING_BETTER_TELEGRAM_MCP_TOKEN}"})

    def test_http_entry_loads_with_token(self) -> None:
        with _swap_env("BETTER_TELEGRAM_MCP_TOKEN", "secret-token"):
            with patch(
                "core.orchestra_agents.backends.sgr._mcp_remote_loader.create_remote_server"
            ) as mock_create:
                server = object()
                mock_create.return_value = server
                servers, schemas = mcp_loader.load_mcp_from_config(
                    _make_http_config(token="secret-token")
                )
                self.assertIs(servers["telegram_send"], server)
                self.assertEqual(
                    schemas,
                    [{"name": "telegram_send", "description": "Remote tool via telegram_relay"}],
                )

    def test_http_entry_skips_empty_token(self) -> None:
        with _swap_env("BETTER_TELEGRAM_MCP_TOKEN", ""):
            with patch(
                "core.orchestra_agents.backends.sgr._mcp_remote_loader.create_remote_server"
            ) as mock_create:
                with self.assertLogs(
                    "core.orchestra_agents.backends.sgr._mcp_remote_loader",
                    level="ERROR",
                ) as ctx:
                    servers, schemas = mcp_loader.load_mcp_from_config(_make_http_config(token=""))
                    mock_create.assert_not_called()
                    self.assertEqual(servers, {})
                    self.assertEqual(schemas, [])
                    output = "\n".join(ctx.output)
                self.assertIn("missing bearer_token", output.lower())


if __name__ == "__main__":
    unittest.main()
