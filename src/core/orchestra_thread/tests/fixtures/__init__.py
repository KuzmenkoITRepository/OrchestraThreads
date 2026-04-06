from __future__ import annotations

import unittest
from typing import Any

from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent
from core.orchestra_thread.tests.fixtures.thread_helpers import (
    create_root_thread as create_root_thread,
)
from core.orchestra_thread.tests.fixtures.thread_helpers import (
    delivery_attempted as delivery_attempted,
)
from core.orchestra_thread.tests.fixtures.thread_helpers import (
    load_ready_thread as load_ready_thread,
)


class BaseE2ETestCase(unittest.IsolatedAsyncioTestCase):
    harness: E2EHarness

    async def asyncSetUp(self) -> None:
        self.harness = E2EHarness()
        await self.harness.start()

    async def asyncTearDown(self) -> None:
        await self.harness.stop()


async def add_pair(harness: E2EHarness) -> dict[str, FakeAgent]:
    return {
        "secretary": await harness.add_agent("secretary"),
        "orchestra": await harness.add_agent("orchestra"),
    }


async def send_message(harness: E2EHarness, **payload: Any) -> dict[str, Any]:
    expected_status = int(payload.pop("expected_status", 200))
    return await harness.send_message(payload, expected_status=expected_status)


async def send_notification(
    harness: E2EHarness,
    *,
    expected_status: int = 200,
    **payload: Any,
) -> dict[str, Any]:
    return await harness.send_notification(payload, expected_status=expected_status)


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
