from __future__ import annotations

import unittest
from functools import partial
from typing import Any

from core.orchestra_agents.tests.template_helpers.assertions import _dispatch_and_assert_completed
from core.orchestra_agents.tests.template_helpers.backend_ops import (
    _delivery,
    _read_capture,
    _run_backend_once,
    _start_backend,
)
from core.orchestra_agents.tests.template_helpers.context_assertions import ContextSnapshot
from core.orchestra_agents.tests.template_helpers.fixture import TemplateFixture


async def _collect_initial(backend: Any) -> ContextSnapshot:
    status = await backend.last_status()
    return backend.current_context_id, status


async def _collect_clear(
    fixture: TemplateFixture,
    backend: Any,
    requested_by: str,
) -> ContextSnapshot:
    clear_payload = await backend.clear_context(
        fixture.backend_module.ClearContextRequest(requested_by=requested_by),
    )
    return backend.current_context_id, clear_payload


async def _initial_context_snapshot(fixture: TemplateFixture) -> ContextSnapshot:
    return await _run_backend_once(fixture, _collect_initial)


async def _clear_context_snapshot(
    fixture: TemplateFixture,
    requested_by: str,
) -> ContextSnapshot:
    return await _run_backend_once(
        fixture,
        partial(_collect_clear, fixture, requested_by=requested_by),
    )


async def _status_after_restart(fixture: TemplateFixture) -> ContextSnapshot:
    return await _initial_context_snapshot(fixture)


async def _prompt_after_two_turns(
    test_case: unittest.IsolatedAsyncioTestCase,
    fixture: TemplateFixture,
) -> tuple[str, list[object]]:
    backend = await _start_backend(
        test_case,
        fixture,
        require_tool_call_for_response=True,
    )
    await _dispatch_and_assert_completed(test_case, backend, _delivery())
    await _dispatch_and_assert_completed(
        test_case,
        backend,
        _delivery(event_id="event-2", message_text="What did I ask before?"),
        event_id="event-2",
        recent_entries=3,
    )
    capture = _read_capture(fixture.capture_path)
    status = await backend.last_status()
    prompt = capture["stdin_payload"]["prompt"]
    recent_entries = status["runtime_context"]["recent_entries"]
    return prompt, recent_entries


async def _context_lifecycle_snapshots(
    fixture: TemplateFixture,
    *,
    requested_by: str,
) -> tuple[ContextSnapshot, ContextSnapshot, ContextSnapshot]:
    before = await _initial_context_snapshot(fixture)
    cleared = await _clear_context_snapshot(fixture, requested_by=requested_by)
    restarted = await _status_after_restart(fixture)
    return before, cleared, restarted
