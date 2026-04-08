from __future__ import annotations

import json
import unittest
from datetime import datetime
from typing import cast

from core.scheduler_cron import executor_helpers as eh

_SAMPLE_DATETIME = datetime(2026, 4, 6, 12, 30, 5)  # noqa: WPS432 - test fixture date
_EVENT_DATA = "event_data"


class TestRequiredStr(unittest.TestCase):
    def test_returns_trimmed_value(self) -> None:
        self.assertEqual(eh.required_str("  alpha  ", field="name"), "alpha")

    def test_raises_for_none(self) -> None:
        with self.assertRaisesRegex(ValueError, "name is required"):
            eh.required_str(None, field="name")

    def test_raises_for_whitespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "name is required"):
            eh.required_str("   ", field="name")


class TestDictHelpers(unittest.TestCase):
    """Tests for as_dict, dict_response, and render_json."""

    def test_as_dict_returns_copy(self) -> None:
        payload: dict[str, object] = {"key": "value"}

        copied = eh.as_dict(payload)

        self.assertEqual(copied, payload)
        self.assertIsNot(copied, payload)

    def test_as_dict_empty_for_non_dict(self) -> None:
        self.assertEqual(eh.as_dict([("key", "value")]), {})

    def test_dict_response_returns_copy(self) -> None:
        response: dict[str, object] = {"ok": False, "detail": "x"}

        copied = eh.dict_response(response)

        self.assertEqual(copied, response)
        self.assertIsNot(copied, response)

    def test_dict_response_default_for_non_dict(self) -> None:
        self.assertEqual(eh.dict_response("not-a-dict"), {"ok": True})

    def test_render_json_preserves_unicode(self) -> None:
        payload: dict[str, object] = {"text": "Привет"}

        rendered = eh.render_json(payload)

        self.assertIn("Привет", rendered)
        self.assertNotIn(r"\u041f", rendered)  # noqa: WPS342
        self.assertEqual(json.loads(rendered), payload)

    def test_render_json_datetime_str(self) -> None:
        moment = _SAMPLE_DATETIME
        payload: dict[str, object] = {"created_at": moment}

        rendered = eh.render_json(payload)

        self.assertIn("2026-04-06 12:30:05", rendered)


class TestEventKindAndTarget(unittest.TestCase):
    """Tests for event_kind_from and scheduler_target."""

    def test_kind_default_when_missing(self) -> None:
        self.assertEqual(eh.event_kind_from({}), eh.DEFAULT_EVENT_KIND)

    def test_kind_default_for_blank(self) -> None:
        payload: dict[str, object] = {"event_kind": "   "}
        self.assertEqual(eh.event_kind_from(payload), eh.DEFAULT_EVENT_KIND)

    def test_kind_casts_non_string(self) -> None:
        payload: dict[str, object] = {"event_kind": 42}
        self.assertEqual(eh.event_kind_from(payload), "42")

    def test_target_default_for_none(self) -> None:
        self.assertEqual(eh.scheduler_target(None), eh.DEFAULT_SCHEDULER_AGENT)

    def test_target_returns_trimmed(self) -> None:
        self.assertEqual(eh.scheduler_target("  agent-x  "), "agent-x")

    def test_target_raises_for_blank(self) -> None:
        with self.assertRaisesRegex(ValueError, "target_agent is required"):
            eh.scheduler_target("   ")


class TestDeliveryPayload(unittest.TestCase):
    def test_top_level_structure(self) -> None:
        built = _sample_payload()

        self.assertEqual(built["agent_slug"], "writer")
        self.assertIsInstance(built[_EVENT_DATA], dict)

    def test_event_data_fields(self) -> None:
        built = _sample_payload()
        event_data = cast(dict[str, object], built[_EVENT_DATA])

        self.assertIn("delivery_id", event_data)
        self.assertIn("events", event_data)
        events = cast(list[object], event_data["events"])  # noqa: WPS226 - test assertion
        self.assertEqual(len(events), 1)

    def test_event_item_content(self) -> None:
        evt = _first_event(_sample_payload())

        self.assertEqual(evt["event_kind"], "status")
        self.assertEqual(evt["from_agent_slug"], eh.SCHEDULER_SOURCE)
        self.assertEqual(evt["to_agent_slug"], "writer")
        self.assertEqual(evt["message_text"], "Done")
        self.assertTrue(cast(bool, evt["requires_response"]))

    def test_event_id_format(self) -> None:
        built = _sample_payload()
        evt = _first_event(built)
        event_data = cast(dict[str, object], built[_EVENT_DATA])

        event_id = cast(str, evt["event_id"])
        self.assertTrue(event_id.startswith("scheduler-"))
        self.assertEqual(event_data["delivery_id"], event_id)


def _sample_payload() -> dict[str, object]:
    return eh.delivery_payload(
        agent_slug="writer",
        event_kind="status",
        message_text="Done",
        requires_response=True,
    )


def _first_event(payload: dict[str, object]) -> dict[str, object]:
    """Extract the first event item from a delivery payload."""
    event_data = cast(dict[str, object], payload[_EVENT_DATA])
    events = cast(list[object], event_data["events"])
    return cast(dict[str, object], events[0])


if __name__ == "__main__":
    unittest.main()
