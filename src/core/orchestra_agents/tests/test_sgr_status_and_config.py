from __future__ import annotations

import unittest

from core.orchestra_agents.backends.sgr import config_builder as _config_builder
from core.orchestra_agents.backends.sgr import status_tracking as _status_tracking


class SGRStatusAndConfigTests(unittest.TestCase):
    def test_status_tracking_exposes_counters(self) -> None:
        status = _status_tracking.SGRBackendStatus(
            total_turns=2,
            total_tool_calls=3,
            total_tool_errors=1,
            total_messages_sent=1,
            total_statuses_published=1,
        )

        payload = status.to_dict()

        self.assertEqual(payload["total_turns"], 2)
        self.assertEqual(payload["total_tool_calls"], 3)
        self.assertEqual(payload["total_tool_errors"], 1)
        self.assertEqual(payload["total_messages_sent"], 1)
        self.assertEqual(payload["total_statuses_published"], 1)

    def test_build_settings_accepts_valid_values(self) -> None:
        settings = _config_builder.build_settings(
            {
                "max_reasoning_steps": 4,
                "react_to_inactive": True,
            }
        )

        self.assertEqual(settings.max_reasoning_steps, 4)
        self.assertTrue(settings.react_to_inactive)


if __name__ == "__main__":
    unittest.main()
