from __future__ import annotations

from typing import Any

from core.orchestra_thread.tests.fixtures.e2e_harness import FakeAgent
from core.orchestra_thread.tests.fixtures.e2e_test_case import BaseE2ETestCase
from core.orchestra_thread.tests.fixtures.thread_helpers import (
    create_root_thread,
    load_ready_thread,
)

_SLUG_SECRETARY = "secretary"
_SLUG_ORCHESTRA = "orchestra"
_DEFAULT_MESSAGE = "Prepare a short update."
_KEY_SLUG = "slug"


def assert_summary_payload(case: BaseE2ETestCase, thread: dict[str, Any], thread_id: str) -> None:
    thread_agents = thread["agents"]
    assert isinstance(thread_agents, dict)
    owner = thread_agents["owner"]
    peer = thread_agents["peer"]
    assert isinstance(owner, dict)
    assert isinstance(peer, dict)
    for field_key, expected in (
        ("thread_scope", "root"),
        ("event_count", 1),
        ("pending_delivery_count", 0),
        ("child_thread_count", 0),
    ):
        case.assertEqual(thread[field_key], expected)
    case.assertEqual(owner[_KEY_SLUG], _SLUG_SECRETARY)
    case.assertEqual(peer[_KEY_SLUG], _SLUG_ORCHESTRA)
    case.assertEqual(thread["roles"]["peer_agent_slug"], _SLUG_ORCHESTRA)
    case.assertIn(_SLUG_SECRETARY, thread["pair_label"])
    case.assertIn(_SLUG_ORCHESTRA, thread["pair_label"])
    case.assertEqual(
        thread["last_event"]["message_preview"],
        _DEFAULT_MESSAGE,
    )
    case.assertEqual(thread["thread_id"], thread_id)


def assert_detail_payload(
    case: BaseE2ETestCase,
    thread_detail: dict[str, Any],
    thread_id: str,
) -> None:
    detail_thread = thread_detail["thread"]
    detail_event = thread_detail["events"][0]
    assert isinstance(detail_thread, dict)
    assert isinstance(detail_event, dict)
    for field_key, expected in (
        ("thread_scope", "root"),
        ("event_count", 1),
        ("pending_delivery_count", 0),
        ("child_thread_count", 0),
    ):
        case.assertEqual(detail_thread[field_key], expected)
    case.assertEqual(
        detail_thread["last_event"]["message_preview"],
        _DEFAULT_MESSAGE,
    )
    case.assertEqual(detail_event["from_agent"][_KEY_SLUG], _SLUG_SECRETARY)
    case.assertEqual(detail_event["to_agent"][_KEY_SLUG], _SLUG_ORCHESTRA)
    case.assertTrue(detail_event["requires_action"])
    case.assertTrue(detail_event["requires_response"])
    case.assertEqual(detail_event["message_preview"], _DEFAULT_MESSAGE)
    case.assertEqual(thread_detail["related"]["root_thread"]["thread_id"], thread_id)


async def create_pair_and_root(case: BaseE2ETestCase) -> tuple[FakeAgent, FakeAgent, str]:
    secretary = await case.harness.add_agent(_SLUG_SECRETARY)
    orchestra = await case.harness.add_agent(_SLUG_ORCHESTRA)
    thread_id = await create_root_thread(
        case,
        case.harness,
        owner=secretary,
        peer=orchestra,
        message_text=_DEFAULT_MESSAGE,
    )
    return secretary, orchestra, thread_id


class UiE2ETests(BaseE2ETestCase):
    async def test_root_serves_console_page(self) -> None:
        body, content_type = await self.harness.request_text(method="GET", path="/")
        self.assertIn("Thread Service Console", body)
        self.assertIn("OrchestraThreads", body)
        self.assertIn("/static/thread-service-ui.js", body)
        self.assertIn("text/html", content_type)

    async def test_thread_payloads_are_ui_enriched(self) -> None:
        secretary, orchestra, thread_id = await create_pair_and_root(self)
        thread = await self.harness.wait_for(
            lambda: load_ready_thread(self.harness, thread_id),
            message="thread summary did not reach the enriched UI-ready state",
        )
        assert thread is not None
        thread_detail = await self.harness.get_thread(thread_id)
        assert_summary_payload(self, thread, thread_id)
        assert_detail_payload(self, thread_detail, thread_id)
        self.assertEqual(
            (
                await self.harness.close_thread(
                    owner_agent=secretary,
                    peer_agent=orchestra,
                    thread_id=thread_id,
                    message_text="Closing UI payload test thread.",
                )
            )["thread"]["status"],
            "closed",
        )

    async def test_instruction_endpoint_workflow(self) -> None:
        payload = await self.harness.get_instruction()
        instruction = payload["instruction"]
        self.assertEqual(instruction["instruction_id"], "orchestra_threads_mvp")
        self.assertEqual(instruction["view"], "compact")
        self.assertEqual(instruction["section"], "all")
        self.assertIn("workflow", instruction)
        self.assertIn("routing_rules", instruction)
        self.assertIn("thread_send", instruction["text"])

        routing_instruction = (await self.harness.get_instruction(section="routing"))["instruction"]
        self.assertEqual(routing_instruction["section"], "routing")
        self.assertIn("routing_rules", routing_instruction)
        self.assertNotIn("status_rules", routing_instruction)
