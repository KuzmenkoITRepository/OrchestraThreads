from __future__ import annotations

import unittest
from typing import Any, cast

from core.orchestra_agents import runtime as runtime_contract
from core.orchestra_agents.tests.template_helpers.backend_ops import _wait_for

_EVENT_ID = "event-1"


def _assert_direct_capture(
    test_case: unittest.TestCase,
    backend: Any,
    capture: dict[str, Any],
) -> None:
    active_context = capture["active_context"]
    for actual, expected in (
        (capture["stdin_payload"]["engine"], "codex"),
        (capture["stdin_payload"]["role"], "worker"),
        (capture["stdin_payload"]["engine_opts"]["close_stdin_after_start"], True),
        (capture["context_id_env"], backend.current_context_id),
        (capture["event_id_env"], _EVENT_ID),
        (capture["event_kind_env"], "telegram_message"),
        (active_context["context_id"], backend.current_context_id),
        (active_context["event_id"], _EVENT_ID),
    ):
        test_case.assertEqual(actual, expected)
    test_case.assertNotIn("thread_id", active_context)
    test_case.assertEqual(
        active_context["metadata"]["source_context"]["channel"],
        "telegram",
    )
    test_case.assertEqual(
        capture["compat_active_context_path_env"],
        capture["active_context_path_env"],
    )
    codex_config = cast(str, capture["codex_config"])
    for expected_text in (
        'model_provider = "omniroute"',
        "[mcp_servers.orchestra_threads]",
        "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH",
    ):
        test_case.assertIn(expected_text, codex_config)


def _assert_completed_status(
    test_case: unittest.TestCase,
    backend: Any,
    status: dict[str, Any],
) -> None:
    checks = (
        (status["context_id"], backend.current_context_id),
        (status["runtime_context"]["context_id"], backend.current_context_id),
        (status["last_dispatch_status"], "completed"),
        (status["last_processed_event_id"], "event-1"),
        (status["last_processed_event_kind"], "telegram_message"),
        (status["last_tool_calls"], ["mcp_tool_call"]),
        (status["runtime_state"]["queue_size"], 0),
    )
    for actual, expected in checks:
        test_case.assertEqual(actual, expected)


async def _assert_failed_dispatch(test_case: unittest.TestCase, backend: Any) -> None:
    failed = await _wait_for(
        lambda: (
            backend.last_dispatch_status == "failed"
            and backend.runtime_state.status_snapshot()["failed_queue_size"] == 1
        )
    )
    test_case.assertTrue(failed)


async def _assert_process_active(test_case: unittest.TestCase, backend: Any) -> None:
    active = await _wait_for(
        lambda: backend._active_process is not None and backend._active_process.returncode is None
    )
    test_case.assertTrue(active)


async def _assert_process_stopped(test_case: unittest.TestCase, backend: Any) -> None:
    cleared = await _wait_for(
        lambda: backend._active_process is None or backend._active_process.returncode is not None
    )
    test_case.assertTrue(cleared)


async def _dispatch_and_assert_completed(
    test_case: unittest.TestCase,
    backend: Any,
    delivery: runtime_contract.EventDelivery,
    *,
    event_id: str = "event-1",
    recent_entries: int = 0,
) -> None:
    dispatch_result = await backend.handle_events(delivery)
    test_case.assertTrue(dispatch_result.accepted)
    completed = await _wait_for(
        lambda: _dispatch_completed(backend, event_id=event_id, recent_entries=recent_entries)
    )
    test_case.assertTrue(completed)


def _dispatch_completed(
    backend: Any,
    *,
    event_id: str,
    recent_entries: int,
) -> bool:
    if backend.last_dispatch_status != "completed":
        return False
    if backend.last_processed_event_id != event_id:
        return False
    if not recent_entries:
        return True
    entries = backend.runtime_state.context_snapshot().get("recent_entries") or []
    return len(entries) >= recent_entries
