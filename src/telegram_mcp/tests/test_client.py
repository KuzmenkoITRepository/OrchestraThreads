from __future__ import annotations

import unittest
from typing import Any, cast

from telegram_mcp.telegram_client import _extract_success, _parse_response


class _FakeResponse:
    def __init__(self, status_code: int, json_data: object) -> None:
        self.status_code = status_code
        self.text = str(json_data)
        self._json = json_data

    def json(self) -> object:
        return self._json


class TelegramMCPClientTests(unittest.TestCase):
    def test_parse_response_non_dict_json(self) -> None:
        response = _FakeResponse(200, [1, 2, 3])
        result = _parse_response(cast(Any, response))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unexpected JSON shape")

    def test_extract_success_bad_message_id(self) -> None:
        result = _extract_success({"ok": True, "message_id": "bad", "error": ""})
        self.assertEqual(result["message_id"], 0)

    def test_extract_success_normal(self) -> None:
        result = _extract_success({"ok": True, "message_id": "42", "error": ""})
        self.assertEqual(result, {"ok": True, "message_id": 42, "error": ""})
