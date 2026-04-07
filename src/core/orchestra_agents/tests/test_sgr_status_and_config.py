from __future__ import annotations

import unittest

from agents.sgr.agent_runtime import config_builder as _config_builder
from agents.sgr.agent_runtime import status_tracking as _status_tracking


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

    def test_build_settings_validates_threads_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "threads_url"):
            _config_builder.build_settings({"threads_url": "ftp://bad-url"})

    def test_build_settings_validates_http_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "http_endpoint"):
            _config_builder.build_settings({"http_endpoint": "bad-endpoint"})

    def test_build_settings_accepts_valid_values(self) -> None:
        settings = _config_builder.build_settings(
            {
                "threads_url": "http://threads.example",
                "http_endpoint": "http://agent.example",
                "heartbeat_interval_seconds": 10,
                "max_reasoning_steps": 4,
            }
        )

        self.assertEqual(settings.threads_url, "http://threads.example")
        self.assertEqual(settings.http_endpoint, "http://agent.example")


if __name__ == "__main__":
    unittest.main()
