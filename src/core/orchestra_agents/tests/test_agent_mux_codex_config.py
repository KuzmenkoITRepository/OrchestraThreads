from __future__ import annotations

import unittest

from core.orchestra_agents.agent_mux_runtime.codex_config import _build_openai_base_url


class AgentMuxCodexConfigTests(unittest.TestCase):
    def test_codex_route_policy_uses_codex_prefix(self) -> None:
        self.assertEqual(
            _build_openai_base_url("codex_only", proxy_url="http://proxy"),
            "http://proxy/codex/v1",
        )

    def test_unknown_route_policy_uses_root_path(self) -> None:
        self.assertEqual(
            _build_openai_base_url("unknown_policy", proxy_url="http://proxy"),
            "http://proxy/v1",
        )
