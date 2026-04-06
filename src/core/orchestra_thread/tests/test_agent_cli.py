from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, cast

from aiohttp import web

from core.orchestra_thread.agent_cli import ManualAgentCLI
from core.orchestra_thread.client import OrchestraThreadsClient


@dataclass
class FakeThreadsClient:
    register_calls: list[dict[str, Any]] = field(default_factory=list)
    heartbeat_calls: list[dict[str, Any]] = field(default_factory=list)
    message_calls: list[dict[str, Any]] = field(default_factory=list)
    notification_calls: list[dict[str, Any]] = field(default_factory=list)
    thread_list_calls: list[dict[str, Any]] = field(default_factory=list)
    thread_get_calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def close(self) -> None:
        self.closed = True

    async def register_agent(self, **kwargs: Any) -> dict[str, Any]:
        self.register_calls.append(kwargs)
        return {"success": True, "agent_lease_seconds": 30}

    async def heartbeat(self, *, agent_slug: str) -> dict[str, Any]:
        self.heartbeat_calls.append({"agent_slug": agent_slug})
        return {"success": True}

    async def list_threads(self, *, scope: str = "active", limit: int = 100) -> dict[str, Any]:
        self.thread_list_calls.append({"scope": scope, "limit": limit})
        return {"success": True, "threads": []}

    async def get_thread(self, *, thread_id: str, limit: int | None = None) -> dict[str, Any]:
        self.thread_get_calls.append({"thread_id": thread_id, "limit": limit})
        return {"success": True, "thread": {"thread_id": thread_id}, "events": []}

    async def send_message(self, **payload: Any) -> dict[str, Any]:
        self.message_calls.append(payload)
        resolved_thread_id = payload.get("thread_id") or payload.get("parent_thread_id")
        if resolved_thread_id is None:
            resolved_thread_id = f"thread-{len(self.message_calls)}"
        normalized_payload = dict(payload)
        normalized_payload.setdefault("thread_id", None)
        normalized_payload.setdefault("parent_thread_id", None)
        self.message_calls[-1] = normalized_payload
        return {
            "success": True,
            "created_thread": normalized_payload.get("thread_id") is None,
            "thread": {
                "thread_id": resolved_thread_id,
                "status": "open",
                "scope": "child" if normalized_payload.get("parent_thread_id") else "root",
            },
        }

    async def send_notification(self, **payload: Any) -> dict[str, Any]:
        self.notification_calls.append(payload)
        return {
            "success": True,
            "thread": {
                "thread_id": payload["thread_id"],
                "status": payload["status"],
            },
            "event": {"notification_status": payload["status"]},
        }


class RequestStub:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        return self._payload


def make_cli() -> tuple[ManualAgentCLI, FakeThreadsClient]:
    client = FakeThreadsClient()
    args = type(
        "Args",
        (),
        {
            "slug": "human",
            "service_url": "http://127.0.0.1:8788",
            "listen_host": "127.0.0.1",
            "listen_port": 0,
            "advertise_host": "127.0.0.1",
            "scheme": "http",
            "heartbeat_interval": 60,
            "target": None,
        },
    )()
    cli = ManualAgentCLI(args)
    cli.thread_client = cast(OrchestraThreadsClient, client)
    return cli, client


def make_request(payload: dict[str, Any]) -> web.Request:
    return cast(web.Request, RequestStub(payload))


class ManualAgentCLIMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_command_sets_target(self) -> None:
        cli, client = make_cli()

        await cli._dispatch_command("chat sgr")
        await cli._dispatch_command("Привет, нужен апдейт")

        first_call = client.message_calls[0]
        self.assertEqual(cli.default_target_agent_slug, "sgr")
        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(first_call["to_agent_slug"], "sgr")
        self.assertIsNone(first_call["thread_id"])
        self.assertEqual(first_call["message_text"], "Привет, нужен апдейт")
        self.assertEqual(cli.current_thread_id, "thread-1")

    async def test_plain_text_replies_into_current_thread(self) -> None:
        cli, client = make_cli()
        cli.current_thread_id = "thread-42"
        cli.thread_peers["thread-42"] = "sgr"

        await cli._dispatch_command("Готово, смотри")

        first_call = client.message_calls[0]
        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(first_call["to_agent_slug"], "sgr")
        self.assertEqual(first_call["thread_id"], "thread-42")
        self.assertEqual(first_call["message_text"], "Готово, смотри")

    async def test_plain_text_strips_terminal_surrogates(self) -> None:
        cli, client = make_cli()
        cli.current_thread_id = "thread-42"
        cli.thread_peers["thread-42"] = "sgr"

        await cli._dispatch_command("\udcd1close")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0]["message_text"], "close")

    async def test_at_prefix_sends_to_explicit_target(self) -> None:
        cli, client = make_cli()

        await cli._dispatch_command("@researcher Проверь, пожалуйста")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0]["to_agent_slug"], "researcher")
        self.assertEqual(client.message_calls[0]["message_text"], "Проверь, пожалуйста")
        self.assertEqual(cli.default_target_agent_slug, "researcher")


class ManualAgentCLIStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactive_event_keeps_known_peer(self) -> None:
        cli, _ = make_cli()
        cli.current_thread_id = "thread-42"
        cli.thread_peers["thread-42"] = "secretary"
        cli.default_target_agent_slug = "secretary"

        request = make_request(
            {
                "events": [
                    {
                        "thread_id": "thread-42",
                        "sequence_no": 2,
                        "event_kind": "inactive",
                        "from_agent_slug": "orchestra_threads",
                        "to_agent_slug": "human",
                        "message_text": "No new activity.",
                    }
                ]
            }
        )

        response = await cli._handle_event(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(cli.current_thread_id, "thread-42")
        self.assertEqual(cli.thread_peers["thread-42"], "secretary")
        self.assertEqual(cli.default_target_agent_slug, "secretary")

    async def test_leave_clears_target_and_thread(self) -> None:
        cli, _ = make_cli()
        cli.default_target_agent_slug = "sgr"
        cli.current_thread_id = "thread-1"

        await cli._dispatch_command("leave")

        self.assertIsNone(cli.default_target_agent_slug)
        self.assertIsNone(cli.current_thread_id)

    async def test_start_autobinds_free_port(self) -> None:
        cli, client = make_cli()

        await cli.start()
        self.addAsyncCleanup(cli.stop)

        self.assertEqual(len(client.register_calls), 1)
        self.assertGreater(cli.listen_port, 0)
        self.assertIn(f":{cli.listen_port}", client.register_calls[0]["base_url"])


class OrchestraThreadsClientSurfaceTests(unittest.TestCase):
    def test_client_keeps_threads_default_url(self) -> None:
        client = OrchestraThreadsClient(base_url="http://127.0.0.1:8788")
        self.assertEqual(client.base_url, "http://127.0.0.1:8788")
