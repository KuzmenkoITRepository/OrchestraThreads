"""Assertion helpers for SGR backend tests."""

from __future__ import annotations

import unittest
from typing import Any

_JsonDict = dict[str, Any]


def _assert_message_event_result(
    test_case: unittest.IsolatedAsyncioTestCase,
    observed: _JsonDict,
) -> None:
    test_case.assertEqual(
        observed,
        {
            "accepted": True,
            "chat_requests": 3,
            "model": "MiniMax-M2.7",
            "message": "Draft ready for handoff.",
            "sent": 1,
            "tool_calls": 2,
            "last_peer": "secretary",
            "last_reply": "Draft ready for handoff.",
            "last_action": True,
        },
    )


def _assert_inactive_delivery_result(
    test_case: unittest.IsolatedAsyncioTestCase,
    dispatch_result: Any,
    notification_calls: list[_JsonDict],
) -> None:
    test_case.assertTrue(dispatch_result.accepted)
    test_case.assertEqual(len(notification_calls), 1)
    test_case.assertEqual(notification_calls[0]["status"], "in_progress")
    test_case.assertEqual(dispatch_result.details["statuses_published"], 1)
    test_case.assertEqual(dispatch_result.details["published_status"], "in_progress")
