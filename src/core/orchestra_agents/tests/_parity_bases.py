"""Base test classes for backend semantic parity tests."""

from __future__ import annotations

import unittest

from core.orchestra_agents.tests._parity_helpers import (
    BootedApp,
    boot,
    evt_payload,
)

_SGR = "sgr_minimax"


class LifecycleBase(unittest.IsolatedAsyncioTestCase):
    """Lifecycle invariants: healthz, stop, clear_context."""

    backend_type: str = _SGR

    async def asyncSetUp(self) -> None:
        self._booted: BootedApp = await boot(self.backend_type)

    async def asyncTearDown(self) -> None:
        await self._booted.close()

    async def test_healthz_ok(self) -> None:
        resp = await self._booted.get("/healthz")
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(resp["context_id"])

    async def test_stop_success(self) -> None:
        resp = await self._booted.post("/stop", {"reason": "x"})
        self.assertTrue(resp["success"])

    async def test_stop_then_event(self) -> None:
        await self._booted.post("/stop", {"reason": "x"})
        resp = await self._booted.post("/event", evt_payload("d-post"))
        self.assertTrue(resp["accepted"])

    async def test_clear_context(self) -> None:
        before = await self._booted.get("/healthz")
        cleared = await self._booted.post(
            "/clear_context",
            {"requested_by": "t"},
        )
        self.assertTrue(cleared["success"])
        self.assertNotEqual(cleared["context_id"], before["context_id"])


class DeliveryBase(unittest.IsolatedAsyncioTestCase):
    """Delivery invariants: event, duplicate, last_status."""

    backend_type: str = _SGR

    async def asyncSetUp(self) -> None:
        self._booted: BootedApp = await boot(self.backend_type)

    async def asyncTearDown(self) -> None:
        await self._booted.close()

    async def test_event_accepted(self) -> None:
        resp = await self._booted.post("/event", evt_payload("d-1"))
        self.assertTrue(resp["accepted"])

    # DIVERGENCE: sgr does not track duplicate delivery_ids
    # DIVERGENCE: opencode does not track duplicate delivery_ids
    async def test_event_duplicate(self) -> None:
        payload = evt_payload("d-dup")
        await self._booted.post("/event", payload)
        second = await self._booted.post("/event", payload)
        self.assertTrue(second.get("duplicate"))

    async def test_last_status(self) -> None:
        await self._booted.post("/event", evt_payload("d-s1"))
        status = await self._booted.get("/last_status")
        self.assertEqual(status["last_delivery_id"], "d-s1")

    async def test_clear_resets(self) -> None:
        """After clear_context, last_status delivery fields reset."""
        await self._booted.post("/event", evt_payload("d-pre"))
        await self._booted.post("/clear_context", {"requested_by": "t"})
        status = await self._booted.get("/last_status")
        self.assertIsNone(status.get("last_delivery_id"))
