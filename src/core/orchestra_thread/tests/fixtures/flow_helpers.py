"""Helpers for thread flow E2E tests."""

from __future__ import annotations

import unittest
from typing import Any

from core.orchestra_thread.tests.fixtures import (
    delivery_attempted,
    send_message,
    send_notification,
)
from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent


async def assert_child_cascade(
    case: unittest.TestCase,
    harness: E2EHarness,
    *,
    owner: FakeAgent,
    peer: FakeAgent,
    cascade_ctx: tuple[FakeAgent, str, str],
) -> None:
    """Assert root closure cascades to child thread."""
    specialist, root_thread_id, child_thread_id = cascade_ctx
    closed = await _close_root_for_cascade(
        harness,
        owner=owner,
        peer=peer,
        thread_id=root_thread_id,
    )
    case.assertEqual(closed["thread"]["status"], "closed")
    await harness.wait_for(
        lambda: specialist.stops,
        message="specialist did not receive stop from child cascade",
    )
    case.assertEqual(specialist.stops[-1]["thread_id"], child_thread_id)

    child_state = await harness.get_thread(child_thread_id)
    case.assertEqual(child_state["thread"]["status"], "closed")
    case.assertEqual(child_state["thread"]["parent_thread_id"], root_thread_id)


async def _close_root_for_cascade(
    harness: E2EHarness,
    *,
    owner: FakeAgent,
    peer: FakeAgent,
    thread_id: str,
) -> dict[str, Any]:
    return await send_notification(
        harness,
        from_agent_slug=owner.slug,
        to_agent_slug=peer.slug,
        thread_id=thread_id,
        status="closed",
        message_text="Stop work.",
    )


async def assert_inactivity_retry(
    case: unittest.TestCase,
    harness: E2EHarness,
    *,
    secretary: FakeAgent,
    orchestra: FakeAgent,
    thread_id: str,
) -> None:
    """Assert inactivity wakeup and retry after agent restart."""
    await _verify_inactivity_wakeup(case, harness, secretary=secretary, thread_id=thread_id)
    await _retry_after_restart(
        case,
        harness,
        secretary=secretary,
        orchestra=orchestra,
        thread_id=thread_id,
    )


async def _verify_inactivity_wakeup(
    case: unittest.TestCase,
    harness: E2EHarness,
    *,
    secretary: FakeAgent,
    thread_id: str,
) -> None:
    await harness.wait_for(
        lambda: any(event.get("event_kind") == "inactive" for event in secretary.events),
        timeout=6.0,
        message="secretary did not receive inactivity wakeup",
    )
    inactivity_event = next(
        event for event in secretary.events if event.get("event_kind") == "inactive"
    )
    case.assertEqual(inactivity_event["thread_id"], thread_id)


async def _retry_after_restart(
    case: unittest.TestCase,
    harness: E2EHarness,
    *,
    secretary: FakeAgent,
    orchestra: FakeAgent,
    thread_id: str,
) -> None:
    await orchestra.stop()
    retry_payload = await send_message(
        harness,
        from_agent_slug=secretary.slug,
        to_agent_slug=orchestra.slug,
        message_text="Deliver this after restart.",
    )
    retry_thread_id = str(retry_payload["thread"]["thread_id"])
    case.assertEqual(retry_thread_id, thread_id)

    await harness.wait_for(
        lambda: delivery_attempted(harness, retry_thread_id),
        timeout=4.0,
        message="pending event was not retried while orchestra was offline",
    )
    await _verify_restart_delivery(
        case,
        harness,
        orchestra=orchestra,
        retry_thread_id=retry_thread_id,
    )


async def _verify_restart_delivery(
    case: unittest.TestCase,
    harness: E2EHarness,
    *,
    orchestra: FakeAgent,
    retry_thread_id: str,
) -> None:
    event_count_before = len(orchestra.events)
    await orchestra.start()
    await harness.register_agent(orchestra)
    await harness.wait_for(
        lambda: len(orchestra.events) > event_count_before,
        timeout=6.0,
        message="retried event was not delivered after orchestra restart",
    )
    case.assertEqual(orchestra.events[-1]["message_text"], "Deliver this after restart.")
