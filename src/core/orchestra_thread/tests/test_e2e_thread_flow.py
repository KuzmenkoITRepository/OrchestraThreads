from __future__ import annotations

from dataclasses import dataclass

from core.orchestra_thread.tests.fixtures import (
    BaseE2ETestCase,
    create_root_thread,
    send_message,
    send_notification,
    wait_for_events,
)
from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent
from core.orchestra_thread.tests.fixtures.flow_helpers import (
    assert_child_cascade,
    assert_inactivity_retry,
)


@dataclass(frozen=True)
class AgentPair:
    secretary: FakeAgent
    orchestra: FakeAgent


async def agent_pair(harness: E2EHarness) -> AgentPair:
    return AgentPair(
        secretary=await harness.add_agent("secretary"),
        orchestra=await harness.add_agent("orchestra"),
    )


async def close_thread(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    pair: AgentPair,
    thread_id: str,
    message_text: str,
) -> None:
    closed = await harness.close_thread(
        owner_agent=pair.secretary,
        peer_agent=pair.orchestra,
        thread_id=thread_id,
        message_text=message_text,
    )
    case.assertEqual(closed["thread"]["status"], "closed")


async def assert_reply_and_reuse(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    pair: AgentPair,
    thread_id: str,
) -> None:
    reply = await send_message(
        harness,
        from_agent_slug=pair.orchestra.slug,
        to_agent_slug=pair.secretary.slug,
        thread_id=thread_id,
        message_text="Done. Here is the update.",
    )
    case.assertEqual(reply["thread"]["thread_id"], thread_id)
    await wait_for_events(
        harness,
        pair.secretary,
        message="secretary did not receive the reply on the root thread",
    )
    case.assertEqual(pair.secretary.events[-1]["thread_id"], thread_id)

    reused = await send_message(
        harness,
        from_agent_slug=pair.secretary.slug,
        to_agent_slug=pair.orchestra.slug,
        message_text="One more thing.",
    )
    case.assertFalse(reused["created_thread"])
    case.assertEqual(reused["thread"]["thread_id"], thread_id)

    threads_payload = await harness.list_threads(scope="active")
    active_roots = [item for item in threads_payload["threads"] if item["scope"] == "root"]
    case.assertEqual(len(active_roots), 1)
    case.assertEqual(active_roots[0]["thread_id"], thread_id)


async def assert_status_controls(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    pair: AgentPair,
    thread_id: str,
) -> None:
    review = await send_notification(
        harness,
        from_agent_slug=pair.orchestra.slug,
        to_agent_slug=pair.secretary.slug,
        thread_id=thread_id,
        status="review",
        message_text="Ready for handoff.",
    )
    case.assertEqual(review["thread"]["status"], "review")
    await harness.wait_for(
        lambda: any(
            event.get("notification_status") == "review" for event in pair.secretary.events
        ),
        message="secretary did not receive the review notification",
    )

    invalid_done = await send_notification(
        harness,
        from_agent_slug=pair.orchestra.slug,
        to_agent_slug=pair.secretary.slug,
        thread_id=thread_id,
        status="done",
        message_text="Done.",
        expected_status=409,
    )
    case.assertIn("cannot publish done", invalid_done["error"])

    closed = await send_notification(
        harness,
        from_agent_slug=pair.secretary.slug,
        to_agent_slug=pair.orchestra.slug,
        thread_id=thread_id,
        status="closed",
        message_text="Closing thread.",
    )
    case.assertEqual(closed["thread"]["status"], "closed")
    await harness.wait_for(
        lambda: pair.orchestra.stops,
        message="orchestra did not receive stop after thread closure",
    )
    case.assertEqual(pair.orchestra.stops[-1]["thread_id"], thread_id)


async def create_child_and_assert(
    case: BaseE2ETestCase,
    harness: E2EHarness,
    pair: AgentPair,
    specialist: FakeAgent,
    root_thread_id: str,
) -> str:
    child = await send_message(
        harness,
        from_agent_slug=pair.orchestra.slug,
        to_agent_slug=specialist.slug,
        parent_thread_id=root_thread_id,
        message_text="Check one detail.",
    )
    child_thread_id = str(child["thread"]["thread_id"])
    case.assertNotEqual(child_thread_id, root_thread_id)
    case.assertEqual(child["thread"]["parent_thread_id"], root_thread_id)
    case.assertEqual(child["thread"]["root_thread_id"], root_thread_id)

    await wait_for_events(
        harness,
        specialist,
        message="specialist did not receive the child-thread message",
    )
    case.assertEqual(specialist.events[-1]["thread_id"], child_thread_id)
    return child_thread_id


class ThreadFlowE2ETests(BaseE2ETestCase):
    async def test_root_thread_reply_and_reuse(self) -> None:
        pair = await agent_pair(self.harness)
        root_thread_id = await create_root_thread(
            self,
            self.harness,
            owner=pair.secretary,
            peer=pair.orchestra,
            message_text="Prepare a short update.",
        )
        await assert_reply_and_reuse(self, self.harness, pair, root_thread_id)
        await close_thread(
            self,
            self.harness,
            pair,
            root_thread_id,
            "Closing root test thread.",
        )

    async def test_message_text_sanitizes_terminal_garbage(self) -> None:
        pair = await agent_pair(self.harness)
        thread_id = await create_root_thread(
            self,
            self.harness,
            owner=pair.secretary,
            peer=pair.orchestra,
            message_text="\u041f\u0440\u0438\u0432\u0435\u0442! \udcd0\u041a\u0442\u043e \u0442\u044b?",
        )
        self.assertEqual(pair.orchestra.events[-1]["message_text"], "Привет! Кто ты?")

        detail = await self.harness.get_thread(thread_id)
        self.assertEqual(detail["events"][0]["message_text"], "Привет! Кто ты?")
        await close_thread(
            self,
            self.harness,
            pair,
            thread_id,
            "Closing sanitize-message test thread.",
        )

    async def test_status_controls_close_and_stop(self) -> None:
        pair = await agent_pair(self.harness)
        thread_id = await create_root_thread(
            self,
            self.harness,
            owner=pair.secretary,
            peer=pair.orchestra,
            message_text="Prepare a short update.",
        )
        await assert_status_controls(self, self.harness, pair, thread_id)

        after_close = await send_message(
            self.harness,
            from_agent_slug=pair.secretary.slug,
            to_agent_slug=pair.orchestra.slug,
            thread_id=thread_id,
            message_text="Should fail after close.",
            expected_status=409,
        )
        self.assertIn("already terminal", after_close["error"])

    async def test_child_thread_creation_and_cascade(self) -> None:
        pair = await agent_pair(self.harness)
        specialist = await self.harness.add_agent("specialist")
        root_thread_id = await create_root_thread(
            self,
            self.harness,
            owner=pair.secretary,
            peer=pair.orchestra,
            message_text="Coordinate a specialist.",
        )
        child_thread_id = await create_child_and_assert(
            self,
            self.harness,
            pair,
            specialist,
            root_thread_id,
        )
        await assert_child_cascade(
            self,
            self.harness,
            owner=pair.secretary,
            peer=pair.orchestra,
            cascade_ctx=(specialist, root_thread_id, child_thread_id),
        )

    async def test_inactivity_retry_after_restart(self) -> None:
        pair = await agent_pair(self.harness)
        inactivity_thread_id = await create_root_thread(
            self,
            self.harness,
            owner=pair.secretary,
            peer=pair.orchestra,
            message_text="Ping and wait.",
        )
        await assert_inactivity_retry(
            self,
            self.harness,
            secretary=pair.secretary,
            orchestra=pair.orchestra,
            thread_id=inactivity_thread_id,
        )
        await close_thread(
            self,
            self.harness,
            pair,
            inactivity_thread_id,
            "Closing inactivity-retry test thread.",
        )
