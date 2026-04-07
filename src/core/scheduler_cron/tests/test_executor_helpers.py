from __future__ import annotations

import json
import unittest
from datetime import datetime
from typing import cast

from core.scheduler_cron.executor_helpers import (
    DEFAULT_EVENT_KIND,
    DEFAULT_SCHEDULER_AGENT,
    SCHEDULER_SOURCE,
    as_dict,
    delivery_payload,
    dict_response,
    event_kind_from,
    render_json,
    required_str,
    scheduler_target,
)


class TestExecutorHelpers(unittest.TestCase):
    def test_required_str_returns_trimmed_value(self) -> None:
        self.assertEqual(required_str("  alpha  ", field="name"), "alpha")

    def test_required_str_raises_for_none(self) -> None:
        with self.assertRaisesRegex(ValueError, "name is required"):
            required_str(None, field="name")

    def test_required_str_raises_for_whitespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "name is required"):
            required_str("   ", field="name")

    def test_as_dict_returns_dict_copy_for_dict_input(self) -> None:
        payload: dict[str, object] = {"key": "value"}

        result = as_dict(payload)

        self.assertEqual(result, payload)
        self.assertIsNot(result, payload)

    def test_as_dict_returns_empty_dict_for_non_dict(self) -> None:
        self.assertEqual(as_dict([("key", "value")]), {})

    def test_render_json_uses_unicode_without_ascii_escaping(self) -> None:
        payload: dict[str, object] = {"text": "Привет"}

        rendered = render_json(payload)

        self.assertIn("Привет", rendered)
        self.assertNotIn("\\u041f", rendered)
        self.assertEqual(json.loads(rendered), payload)

    def test_render_json_serializes_datetime_with_default_str(self) -> None:
        moment = datetime(2026, 4, 6, 12, 30, 5)
        payload: dict[str, object] = {"created_at": moment}

        rendered = render_json(payload)

        self.assertIn("2026-04-06 12:30:05", rendered)

    def test_event_kind_from_returns_default_when_missing(self) -> None:
        self.assertEqual(event_kind_from({}), DEFAULT_EVENT_KIND)

    def test_event_kind_from_returns_default_for_blank_string(self) -> None:
        payload: dict[str, object] = {"event_kind": "   "}

        self.assertEqual(event_kind_from(payload), DEFAULT_EVENT_KIND)

    def test_event_kind_from_casts_non_string_values(self) -> None:
        payload: dict[str, object] = {"event_kind": 42}

        self.assertEqual(event_kind_from(payload), "42")

    def test_scheduler_target_returns_default_for_none(self) -> None:
        self.assertEqual(scheduler_target(None), DEFAULT_SCHEDULER_AGENT)

    def test_scheduler_target_returns_trimmed_value(self) -> None:
        self.assertEqual(scheduler_target("  agent-x  "), "agent-x")

    def test_scheduler_target_raises_for_invalid_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "target_agent is required"):
            scheduler_target("   ")

    def test_dict_response_returns_dict_copy_for_dict_input(self) -> None:
        response: dict[str, object] = {"ok": False, "detail": "x"}

        result = dict_response(response)

        self.assertEqual(result, response)
        self.assertIsNot(result, response)

    def test_dict_response_returns_default_for_non_dict(self) -> None:
        self.assertEqual(dict_response("not-a-dict"), {"ok": True})

    def test_delivery_payload_builds_expected_structure(self) -> None:
        result = delivery_payload(
            agent_slug="writer",
            event_kind="status",
            message_text="Done",
            requires_response=True,
        )

        self.assertEqual(result["agent_slug"], "writer")
        event_data = result["event_data"]
        self.assertIsInstance(event_data, dict)

        event_data_dict = cast(dict[str, object], event_data)
        self.assertIn("delivery_id", event_data_dict)
        self.assertIn("events", event_data_dict)

        events = event_data_dict["events"]
        self.assertIsInstance(events, list)
        events_list = cast(list[object], events)
        self.assertEqual(len(events_list), 1)

        event_item = events_list[0]
        self.assertIsInstance(event_item, dict)

        event_item_dict = cast(dict[str, object], event_item)
        self.assertEqual(event_item_dict["event_kind"], "status")
        self.assertEqual(event_item_dict["from_agent_slug"], SCHEDULER_SOURCE)
        self.assertEqual(event_item_dict["to_agent_slug"], "writer")
        self.assertEqual(event_item_dict["message_text"], "Done")
        self.assertTrue(cast(bool, event_item_dict["requires_response"]))

        event_id = event_item_dict["event_id"]
        self.assertIsInstance(event_id, str)
        event_id_str = cast(str, event_id)
        self.assertTrue(event_id_str.startswith("scheduler-"))
        self.assertEqual(event_data_dict["delivery_id"], event_id)


if __name__ == "__main__":
    unittest.main()
