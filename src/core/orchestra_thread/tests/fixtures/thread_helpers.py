from __future__ import annotations

import unittest
from typing import Any

from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent


async def send_message(harness: E2EHarness, **payload: Any) -> dict[str, Any]:
    expected_status = int(payload.pop("expected_status", 200))
    return await harness.send_message(payload, expected_status=expected_status)


async def wait_for_events(
    harness: E2EHarness,
    agent: FakeAgent,
    *,
    count: int = 1,
    message: str,
    timeout: float = 5.0,
) -> None:
    await harness.wait_for(
        lambda: len(agent.events) >= count,
        timeout=timeout,
        message=message,
    )


async def create_root_thread(
    case: unittest.TestCase,
    harness: E2EHarness,
    *,
    owner: FakeAgent,
    peer: FakeAgent,
    message_text: str,
) -> str:
    created = await send_message(
        harness,
        from_agent_slug=owner.slug,
        to_agent_slug=peer.slug,
        message_text=message_text,
    )
    thread_id = str(created["thread"]["thread_id"])
    case.assertTrue(created["created_thread"])
    await wait_for_events(
        harness,
        peer,
        message=f"{peer.slug} did not receive the initial root-thread message",
    )
    case.assertEqual(peer.events[-1]["thread_id"], thread_id)
    return thread_id


async def load_ready_thread(harness: E2EHarness, thread_id: str) -> dict[str, Any] | None:
    threads_payload = await harness.list_threads(scope="active")
    thread_item = next(
        (item for item in threads_payload["threads"] if item["thread_id"] == thread_id),
        None,
    )
    if not isinstance(thread_item, dict):
        return None
    if thread_item.get("pending_delivery_count") != 0:
        return None
    if not thread_item.get("last_event"):
        return None
    return thread_item


async def delivery_attempted(harness: E2EHarness, thread_id: str) -> bool:
    thread = await harness.service.store.get_thread(thread_id)
    if not thread:
        return False
    events = await harness.service.store.list_thread_events(thread_id=thread_id, limit=20)
    if not events:
        return False
    return int(events[-1]["delivery_attempt_count"]) >= 1
