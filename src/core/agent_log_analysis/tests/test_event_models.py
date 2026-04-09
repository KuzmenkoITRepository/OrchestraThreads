"""Tests for event envelope, inference, and action DTO modules."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from core.agent_log_analysis.event_action import (
    ActionKind,
    ActionPayload,
    ActionStatus,
)
from core.agent_log_analysis.event_envelope import EventEnvelope, EventType
from core.agent_log_analysis.event_inference import (
    InferencePayload,
    InferenceRequestKind,
    InferenceStatus,
)


class TestEventEnvelope(unittest.TestCase):
    """Test event envelope DTO."""

    def test_frozen(self) -> None:
        env = _make_envelope()
        with self.assertRaises(AttributeError):
            env.event_id = "changed"  # type: ignore[misc]

    def test_event_type_enum(self) -> None:
        self.assertEqual(EventType.inference_event.value, "inference_event")
        self.assertEqual(EventType.action_event.value, "action_event")

    def test_default_labels_empty(self) -> None:
        env = _make_envelope()
        self.assertEqual(env.labels, {})


class TestInferencePayload(unittest.TestCase):
    """Test inference payload DTO."""

    def test_request_kind_enum(self) -> None:
        kinds = [m.value for m in InferenceRequestKind]
        self.assertIn("chat", kinds)
        self.assertIn("completion", kinds)
        self.assertIn("tool-selection", kinds)
        self.assertIn("other", kinds)

    def test_status_enum(self) -> None:
        statuses = [m.value for m in InferenceStatus]
        self.assertIn("success", statuses)
        self.assertIn("error", statuses)
        self.assertIn("timeout", statuses)
        self.assertIn("cancelled", statuses)

    def test_frozen(self) -> None:
        payload = InferencePayload(model_name="gpt-4")
        with self.assertRaises(AttributeError):
            payload.model_name = "x"  # type: ignore[misc]


class TestActionPayload(unittest.TestCase):
    """Test action payload DTO."""

    def test_action_kind_enum_values(self) -> None:
        kinds = [m.value for m in ActionKind]
        expected = [
            "tool_call",
            "message_send",
            "http_request",
            "state_transition",
            "task_update",
            "other",
        ]
        for exp in expected:
            self.assertIn(exp, kinds)

    def test_status_has_rejected(self) -> None:
        statuses = [m.value for m in ActionStatus]
        self.assertIn("rejected", statuses)

    def test_frozen(self) -> None:
        payload = ActionPayload(action_kind=ActionKind.tool_call)
        with self.assertRaises(AttributeError):
            payload.action_kind = ActionKind.other  # type: ignore[misc]


def _make_envelope() -> EventEnvelope:
    now = datetime.now(tz=UTC)
    return EventEnvelope(
        event_id="evt-1",
        event_type=EventType.inference_event,
        occurred_at=now,
        received_at=now,
        agent_slug="test-agent",
    )
