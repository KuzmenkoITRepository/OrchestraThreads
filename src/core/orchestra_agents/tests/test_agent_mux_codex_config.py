from __future__ import annotations

import unittest

from core.orchestra_agents.backends.agent_mux.codex_config_helpers import (
    base_config_lines,
    build_openai_base_url,
)


class AgentMuxCodexConfigTests(unittest.TestCase):
    def test_codex_config_disables_web_search(self) -> None:
        self.assertIn(
            'web_search = "disabled"',
            base_config_lines(
                model="cx/gpt-5.1-codex-mini",
                base_url="http://proxy",
                env_key="OMNIROUTE_API_KEY",
            ),
        )

    def test_codex_config_uses_omniroute_api_key(self) -> None:
        self.assertIn(
            'env_key = "OMNIROUTE_API_KEY"',
            base_config_lines(
                model="cx/gpt-5.1-codex-mini",
                base_url="http://proxy",
                env_key="OMNIROUTE_API_KEY",
            ),
        )

    def test_codex_config_omits_env_key_when_empty(self) -> None:
        self.assertNotIn(
            'env_key = "OMNIROUTE_API_KEY"',
            base_config_lines(
                model="cx/gpt-5.1-codex-mini",
                base_url="http://proxy",
                env_key=None,
            ),
        )

    def test_codex_route_policy_uses_codex_prefix(self) -> None:
        self.assertEqual(
            build_openai_base_url("codex_only", proxy_url="http://proxy"),
            "http://proxy/codex/v1",
        )

    def test_minimax_route_policy_uses_root_path(self) -> None:
        self.assertEqual(
            build_openai_base_url("minimax_only", proxy_url="http://proxy"),
            "http://proxy/v1",
        )

    def test_unknown_route_policy_uses_root_path(self) -> None:
        self.assertEqual(
            build_openai_base_url("unknown_policy", proxy_url="http://proxy"),
            "http://proxy/v1",
        )
