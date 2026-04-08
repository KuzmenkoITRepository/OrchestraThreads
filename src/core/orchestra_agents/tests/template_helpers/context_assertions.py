from __future__ import annotations

import unittest
from typing import Any

JSONMap = dict[str, Any]
ContextSnapshot = tuple[str, JSONMap]
ContextDetails = tuple[str, JSONMap, JSONMap]
_CONTEXT_ID_KEY = "context_id"
_RECENT_ENTRIES_KEY = "recent_entries"


def _context_details(snapshot: ContextSnapshot) -> ContextDetails:
    context_id, payload = snapshot
    runtime_context = payload["runtime_context"]
    return context_id, payload, runtime_context


def _assert_before_and_cleared(
    test_case: unittest.TestCase,
    before_details: ContextDetails,
    cleared_details: ContextDetails,
) -> None:
    before_context_id = before_details[0]
    cleared_context_id = cleared_details[0]
    for actual, expected in (
        (before_details[1][_CONTEXT_ID_KEY], before_context_id),
        (before_details[2][_RECENT_ENTRIES_KEY], []),
        (cleared_details[1]["previous_context_id"], before_context_id),
        (cleared_details[1][_CONTEXT_ID_KEY], cleared_context_id),
        (cleared_details[2][_CONTEXT_ID_KEY], cleared_context_id),
        (cleared_details[2][_RECENT_ENTRIES_KEY], []),
    ):
        test_case.assertEqual(actual, expected)
    test_case.assertNotEqual(cleared_context_id, before_context_id)


def _assert_restarted(
    test_case: unittest.TestCase,
    before_details: ContextDetails,
    cleared_details: ContextDetails,
    restarted_details: ContextDetails,
) -> None:
    for actual, expected in (
        (restarted_details[0], cleared_details[0]),
        (restarted_details[2][_CONTEXT_ID_KEY], cleared_details[0]),
        (restarted_details[2]["previous_context_id"], before_details[0]),
        (restarted_details[2][_RECENT_ENTRIES_KEY], []),
    ):
        test_case.assertEqual(actual, expected)


def _assert_context_lifecycle(
    test_case: unittest.TestCase,
    before: ContextSnapshot,
    cleared: ContextSnapshot,
    restarted: ContextSnapshot,
) -> None:
    before_details = _context_details(before)
    cleared_details = _context_details(cleared)
    _assert_before_and_cleared(test_case, before_details, cleared_details)
    _assert_restarted(test_case, before_details, cleared_details, _context_details(restarted))
