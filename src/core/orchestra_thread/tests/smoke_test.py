"""Basic end-to-end smoke test for the OrchestraThreads MVP."""

from __future__ import annotations

import json
import os
import sys

from core.orchestra_thread.tests.fixtures.e2e_harness import E2EHarness, FakeAgent


def _smoke_database_url() -> str:
    return (
        os.getenv("ORCHESTRA_THREADS_TEST_DATABASE_URL")
        or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
        or "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads"
    )


def _emit_result(payload: dict[str, str | int | bool]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


async def _create_initial_thread(harness: E2EHarness) -> tuple[str, FakeAgent, FakeAgent]:
    secretary = await harness.add_agent("secretary")
    orchestra = await harness.add_agent("orchestra")
    created = await harness.send_message(
        {
            "from_agent_slug": "secretary",
            "to_agent_slug": "orchestra",
            "message_text": "Prepare a short update.",
        }
    )
    thread_id = str(created["thread"]["thread_id"])
    await harness.wait_for(
        lambda: orchestra.events,
        message="orchestra did not receive the initial message",
    )
    return thread_id, secretary, orchestra


async def _reply_and_collect(
    harness: E2EHarness,
    *,
    thread_id: str,
    secretary: FakeAgent,
    orchestra: FakeAgent,
) -> dict[str, str | int | bool]:
    await harness.send_message(
        {
            "from_agent_slug": "orchestra",
            "to_agent_slug": "secretary",
            "thread_id": thread_id,
            "message_text": "Done. Here is the update.",
        }
    )
    await harness.wait_for(
        lambda: secretary.events,
        message="secretary did not receive the reply",
    )
    thread_payload = await harness.get_thread(thread_id)
    assert len(thread_payload["events"]) == 2, thread_payload
    return {
        "ok": True,
        "thread_id": thread_id,
        "secretary_events": len(secretary.events),
        "orchestra_events": len(orchestra.events),
    }


async def main() -> None:
    async with E2EHarness(database_url=_smoke_database_url()) as harness:
        thread_id, secretary, orchestra = await _create_initial_thread(harness)
        smoke_result = await _reply_and_collect(
            harness,
            thread_id=thread_id,
            secretary=secretary,
            orchestra=orchestra,
        )
    _emit_result(smoke_result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
