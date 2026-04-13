from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.telegram_events import _http_send_helpers, http_server


class TelegramEventsHttpServerTests(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        app = http_server.build_app()
        app["relay_url"] = "http://relay.test"
        app["bearer_token"] = "secret-token"
        return app

    async def test_send_requires_bearer_token(self) -> None:
        response = await self.client.post("/send", json={"chat_id": 123, "message": "hello"})

        self.assertEqual(response.status, 401)
        self.assertEqual(await response.json(), {"ok": False, "error": "Unauthorized"})

    async def test_send_rejects_incorrect_bearer_token(self) -> None:
        response = await self.client.post(
            "/send",
            headers={"Authorization": "Bearer wrong-token"},
            json={"chat_id": 123, "message": "hello"},
        )

        self.assertEqual(response.status, 401)
        self.assertEqual(await response.json(), {"ok": False, "error": "Unauthorized"})

    async def test_send_accepts_valid_bearer_token(self) -> None:
        mock_execute = AsyncMock()
        mock_execute.return_value = web.json_response({"ok": True, "messageId": 1})
        with patch.object(_http_send_helpers, "execute_send_via_relay", new=mock_execute):
            response = await self.client.post(
                "/send",
                headers={"Authorization": "Bearer secret-token"},
                json={"chat_id": 123, "message": "hello"},
            )

        self.assertEqual(response.status, 200)
        mock_execute.assert_awaited_once_with("http://relay.test", "secret-token", 123, "hello")


if __name__ == "__main__":
    unittest.main()
