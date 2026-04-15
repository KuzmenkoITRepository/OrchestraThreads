from __future__ import annotations

import unittest

from core.orchestra_agents.backends.opencode.config_model import build_root_payload
from core.orchestra_agents.backends.opencode.config_provider import (
    _provider_options,
    build_provider_entry,
)


class OpencodeProviderTests(unittest.TestCase):
    def test_provider_options_use_omniroute(self) -> None:
        options = _provider_options(
            {"omniroute_url": "http://omniroute:20128/", "omniroute_api_key": " direct-key "}
        )

        self.assertEqual(options["baseURL"], "http://omniroute:20128/v1")
        self.assertEqual(options["apiKey"], "direct-key")

    def test_provider_payload_uses_omniroute(self) -> None:
        provider = build_provider_entry(
            "gpt-5.4-mini",
            {
                "omniroute_url": "http://orchestra-omniroute:20128",
                "omniroute_api_key": "direct-key",
            },
        )
        payload = build_root_payload(
            "gpt-5.4-mini",
            {
                "omniroute_url": "http://orchestra-omniroute:20128",
                "omniroute_api_key": "direct-key",
            },
        )

        self.assertEqual(provider["options"]["baseURL"], "http://orchestra-omniroute:20128/v1")
        self.assertEqual(provider["options"]["apiKey"], "direct-key")
        self.assertEqual(payload["provider"]["omniroute"], provider)
        self.assertEqual(payload["model"], "omniroute/gpt-5.4-mini")
