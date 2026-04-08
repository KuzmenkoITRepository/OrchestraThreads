from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, cast

from aiohttp import web

from core.orchestra_thread.agent_cli import ManualAgentCLI
from core.orchestra_thread.client import OrchestraThreadsClient

_KEY_SUCCESS = "success"
_KEY_THREAD_ID = "thread_id"
_KEY_STATUS = "status"
_KEY_TO_AGENT = "to_agent_slug"
_KEY_MESSAGE_TEXT = "message_text"
_AGENT_SGR = "sgr"
_STUB_THREAD_ID = "thread-42"
_AGENT_SECRETARY = "secretary"
_HTTP_OK = 200


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
        return {_KEY_SUCCESS: True, "agent_lease_seconds": 30}

    async def heartbeat(self, *, agent_slug: str) -> dict[str, Any]:
        self.heartbeat_calls.append({"agent_slug": agent_slug})
        return {_KEY_SUCCESS: True}

    async def list_threads(self, *, scope: str = "active", limit: int = 100) -> dict[str, Any]:
        self.thread_list_calls.append({"scope": scope, "limit": limit})
        return {_KEY_SUCCESS: True, "threads": []}

    async def get_thread(self, *, thread_id: str, limit: int | None = None) -> dict[str, Any]:
        self.thread_get_calls.append({_KEY_THREAD_ID: thread_id, "limit": limit})
        return {_KEY_SUCCESS: True, "thread": {_KEY_THREAD_ID: thread_id}, "events": []}

    async def send_message(self, **payload: Any) -> dict[str, Any]:
        self.message_calls.append(payload)
        resolved_thread_id = payload.get(_KEY_THREAD_ID) or payload.get("parent_thread_id")
        if resolved_thread_id is None:
            resolved_thread_id = f"thread-{len(self.message_calls)}"
        normalized_payload = dict(payload)
        normalized_payload.setdefault(_KEY_THREAD_ID, None)
        normalized_payload.setdefault("parent_thread_id", None)
        self.message_calls[-1] = normalized_payload
        return {
            _KEY_SUCCESS: True,
            "created_thread": normalized_payload.get(_KEY_THREAD_ID) is None,
            "thread": {
                _KEY_THREAD_ID: resolved_thread_id,
                _KEY_STATUS: "open",
                "scope": "child" if normalized_payload.get("parent_thread_id") else "root",
            },
        }

    async def send_notification(self, **payload: Any) -> dict[str, Any]:
        self.notification_calls.append(payload)
        return {
            _KEY_SUCCESS: True,
            "thread": {
                _KEY_THREAD_ID: payload[_KEY_THREAD_ID],
                _KEY_STATUS: payload[_KEY_STATUS],
            },
            "event": {"notification_status": payload[_KEY_STATUS]},
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
        self.assertEqual(cli.default_target_agent_slug, _AGENT_SGR)
        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(first_call[_KEY_TO_AGENT], _AGENT_SGR)
        self.assertIsNone(first_call[_KEY_THREAD_ID])
        self.assertEqual(first_call[_KEY_MESSAGE_TEXT], "Привет, нужен апдейт")
        self.assertEqual(cli.current_thread_id, "thread-1")

    async def test_plain_text_replies_into_current_thread(self) -> None:
        cli, client = make_cli()
        cli.current_thread_id = _STUB_THREAD_ID
        cli.thread_peers[_STUB_THREAD_ID] = _AGENT_SGR

        await cli._dispatch_command("Готово, смотри")

        first_call = client.message_calls[0]
        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(first_call[_KEY_TO_AGENT], _AGENT_SGR)
        self.assertEqual(first_call[_KEY_THREAD_ID], _STUB_THREAD_ID)
        self.assertEqual(first_call[_KEY_MESSAGE_TEXT], "Готово, смотри")

    async def test_plain_text_strips_terminal_surrogates(self) -> None:
        cli, client = make_cli()
        cli.current_thread_id = _STUB_THREAD_ID
        cli.thread_peers[_STUB_THREAD_ID] = _AGENT_SGR

        await cli._dispatch_command("\udcd1close")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0][_KEY_MESSAGE_TEXT], "close")

    async def test_at_prefix_sends_to_explicit_target(self) -> None:
        cli, client = make_cli()

        await cli._dispatch_command("@researcher Проверь, пожалуйста")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0][_KEY_TO_AGENT], "researcher")
        self.assertEqual(client.message_calls[0][_KEY_MESSAGE_TEXT], "Проверь, пожалуйста")
        self.assertEqual(cli.default_target_agent_slug, "researcher")


class ManualAgentCLIStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactive_event_keeps_known_peer(self) -> None:
        cli, _ = make_cli()
        cli.current_thread_id = _STUB_THREAD_ID
        cli.thread_peers[_STUB_THREAD_ID] = _AGENT_SECRETARY
        cli.default_target_agent_slug = _AGENT_SECRETARY

        request = make_request(
            {
                "events": [
                    {
                        _KEY_THREAD_ID: _STUB_THREAD_ID,
                        "sequence_no": 2,
                        "event_kind": "inactive",
                        "from_agent_slug": "orchestra_threads",
                        _KEY_TO_AGENT: "human",
                        _KEY_MESSAGE_TEXT: "No new activity.",
                    }
                ]
            }
        )

        response = await cli._handle_event(request)

        self.assertEqual(response.status, _HTTP_OK)
        self.assertEqual(cli.current_thread_id, _STUB_THREAD_ID)
        self.assertEqual(cli.thread_peers[_STUB_THREAD_ID], _AGENT_SECRETARY)
        self.assertEqual(cli.default_target_agent_slug, _AGENT_SECRETARY)

    async def test_leave_clears_target_and_thread(self) -> None:
        cli, _ = make_cli()
        cli.default_target_agent_slug = _AGENT_SGR
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
