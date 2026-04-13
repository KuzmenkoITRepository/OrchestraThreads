from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web

from core.telegram_events import _http_send_helpers as helpers


class HttpSendHelpersTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_id_structured(self) -> None:
        result = {
            "result": {
                "content": [
                    {"text": {"structuredContent": {"messageId": 12345}}},
                ],
            },
        }

        self.assertEqual(helpers._extract_message_id(result), 12345)

    def test_extract_id_legacy_dict(self) -> None:
        result = {
            "result": {
                "content": [
                    {"text": {"message_id": 67890}},
                ],
            },
        }

        self.assertEqual(helpers._extract_message_id(result), 67890)

    def test_extract_id_numeric_string(self) -> None:
        result = {
            "result": {
                "content": [
                    {"text": "24680"},
                ],
            },
        }

        self.assertEqual(helpers._extract_message_id(result), 24680)

    def test_extract_id_missing(self) -> None:
        result = {
            "result": {
                "content": [
                    {"text": {"structuredContent": {}}},
                    {"text": {"message_id": "not-an-int"}},
                    {"text": ""},
                    "unexpected",
                ],
            },
        }

        self.assertEqual(helpers._extract_message_id(result), 0)

    def test_extract_id_invalid_json(self) -> None:
        result = {
            "result": {
                "content": [
                    {"text": "not-json"},
                ],
            },
        }

        self.assertEqual(helpers._extract_message_id(result), 0)

    async def test_send_relay_bad_status(self) -> None:
        response = MagicMock()
        response.status_code = 503
        response.text = "service unavailable"

        client = MagicMock()
        client.post = AsyncMock(return_value=response)
        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(return_value=client)
        client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch.object(helpers, "httpx", create=True) as mock_httpx:
            mock_httpx.AsyncClient.return_value = client_cm
            response_obj = await helpers.execute_send_via_relay(
                relay_url="http://relay.test",
                bearer_token="token",
                chat_id=100,
                message="hello",
            )

        self.assertIsInstance(response_obj, web.Response)
        self.assertEqual(response_obj.status, 502)
        self.assertEqual(response_obj.text, '{"ok": false, "error": "Relay returned 503"}')

    def test_parse_invalid_json(self) -> None:
        response = MagicMock()
        response.json.side_effect = ValueError("bad json")

        response_obj = helpers._parse_relay_response(response, chat_id=100)

        self.assertIsInstance(response_obj, web.Response)
        self.assertEqual(response_obj.status, 502)
        self.assertEqual(response_obj.text, '{"ok": false, "error": "Invalid response from relay"}')


if __name__ == "__main__":
    unittest.main()
