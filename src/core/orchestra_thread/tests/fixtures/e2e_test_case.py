from __future__ import annotations

import unittest
from typing import Any

from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent

_HTTP_OK = 200


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


async def send_notification(
    harness: E2EHarness,
    *,
    expected_status: int = _HTTP_OK,
    **payload: Any,
) -> dict[str, Any]:
    return await harness.send_notification(payload, expected_status=expected_status)
