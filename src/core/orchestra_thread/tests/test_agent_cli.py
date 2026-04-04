from __future__ import annotations

import unittest
from typing import Any, Optional

from core.orchestra_thread.agent_cli import ManualAgentCLI
from core.orchestra_thread.client import OrchestraThreadsClient


class FakeThreadsClient:
    def __init__(self) -> None:
        self.register_calls: list[dict[str, Any]] = []
        self.heartbeat_calls: list[dict[str, Any]] = []
        self.agent_list_calls = 0
        self.thread_list_calls: list[dict[str, Any]] = []
        self.thread_get_calls: list[dict[str, Any]] = []
        self.message_calls: list[dict[str, Any]] = []
        self.notification_calls: list[dict[str, Any]] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def register_agent(self, **kwargs: Any) -> dict[str, Any]:
        self.register_calls.append(kwargs)
        return {"success": True, "agent_lease_seconds": 30}

    async def heartbeat(self, *, agent_slug: str) -> dict[str, Any]:
        self.heartbeat_calls.append({"agent_slug": agent_slug})
        return {"success": True}

    async def list_agents(self) -> dict[str, Any]:
        self.agent_list_calls += 1
        return {"success": True, "agents": []}

    async def list_threads(self, *, scope: str = "active", limit: int = 100) -> dict[str, Any]:
        self.thread_list_calls.append({"scope": scope, "limit": limit})
        return {"success": True, "threads": []}

    async def get_thread(self, *, thread_id: str, limit: Optional[int] = None) -> dict[str, Any]:
        self.thread_get_calls.append({"thread_id": thread_id, "limit": limit})
        return {"success": True, "thread": {"thread_id": thread_id}, "events": []}

    async def send_message(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        thread_id: Optional[str] = None,
        parent_thread_id: Optional[str] = None,
        client_request_id: Optional[str] = None,
    ) -> dict[str, Any]:
        self.message_calls.append(
            {
                "from_agent_slug": from_agent_slug,
                "to_agent_slug": to_agent_slug,
                "message_text": message_text,
                "thread_id": thread_id,
                "parent_thread_id": parent_thread_id,
                "client_request_id": client_request_id,
            }
        )
        resolved_thread_id = thread_id or parent_thread_id or f"thread-{len(self.message_calls)}"
        return {
            "success": True,
            "created_thread": thread_id is None,
            "thread": {
                "thread_id": resolved_thread_id,
                "status": "open",
                "scope": "child" if parent_thread_id else "root",
            },
        }

    async def send_notification(
        self,
        *,
        from_agent_slug: str,
        to_agent_slug: str,
        thread_id: str,
        status: str,
        message_text: str,
        client_request_id: Optional[str] = None,
    ) -> dict[str, Any]:
        self.notification_calls.append(
            {
                "from_agent_slug": from_agent_slug,
                "to_agent_slug": to_agent_slug,
                "thread_id": thread_id,
                "status": status,
                "message_text": message_text,
                "client_request_id": client_request_id,
            }
        )
        return {
            "success": True,
            "thread": {"thread_id": thread_id, "status": status},
            "event": {"notification_status": status},
        }


class ManualAgentCLITests(unittest.IsolatedAsyncioTestCase):
    def _cli(self) -> tuple[ManualAgentCLI, FakeThreadsClient]:
        client = FakeThreadsClient()
        cli = ManualAgentCLI(
            agent_slug="human",
            service_url="http://127.0.0.1:8788",
            listen_host="127.0.0.1",
            listen_port=0,
            advertise_host="127.0.0.1",
            scheme="http",
            heartbeat_interval_seconds=60,
        )
        cli.thread_client = client  # type: ignore[assignment]
        return cli, client

    async def test_chat_command_sets_target_and_plain_text_sends_message(self) -> None:
        cli, client = self._cli()

        await cli._dispatch_command("chat sgr")
        await cli._dispatch_command("Привет, нужен апдейт")

        self.assertEqual(cli.default_target_agent_slug, "sgr")
        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0]["to_agent_slug"], "sgr")
        self.assertEqual(client.message_calls[0]["thread_id"], None)
        self.assertEqual(client.message_calls[0]["message_text"], "Привет, нужен апдейт")
        self.assertEqual(cli.current_thread_id, "thread-1")

    async def test_plain_text_replies_into_current_thread(self) -> None:
        cli, client = self._cli()
        cli.current_thread_id = "thread-42"
        cli.thread_peers["thread-42"] = "sgr"

        await cli._dispatch_command("Готово, смотри")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0]["to_agent_slug"], "sgr")
        self.assertEqual(client.message_calls[0]["thread_id"], "thread-42")
        self.assertEqual(client.message_calls[0]["message_text"], "Готово, смотри")

    async def test_plain_text_input_strips_terminal_surrogates(self) -> None:
        cli, client = self._cli()
        cli.current_thread_id = "thread-42"
        cli.thread_peers["thread-42"] = "sgr"

        await cli._dispatch_command("\udcd1close")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0]["message_text"], "close")

    async def test_at_prefix_sends_to_explicit_target(self) -> None:
        cli, client = self._cli()

        await cli._dispatch_command("@researcher Проверь, пожалуйста")

        self.assertEqual(len(client.message_calls), 1)
        self.assertEqual(client.message_calls[0]["to_agent_slug"], "researcher")
        self.assertEqual(client.message_calls[0]["message_text"], "Проверь, пожалуйста")
        self.assertEqual(cli.default_target_agent_slug, "researcher")

    async def test_inactive_event_keeps_known_peer_instead_of_service_slug(self) -> None:
        cli, _ = self._cli()
        cli.current_thread_id = "thread-42"
        cli.thread_peers["thread-42"] = "secretary"
        cli.default_target_agent_slug = "secretary"

        class _Request:
            async def json(self) -> dict[str, Any]:
                return {
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

        request = _Request()

        response = await cli._handle_event(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(cli.current_thread_id, "thread-42")
        self.assertEqual(cli.thread_peers["thread-42"], "secretary")
        self.assertEqual(cli.default_target_agent_slug, "secretary")

    async def test_leave_clears_target_and_thread(self) -> None:
        cli, _ = self._cli()
        cli.default_target_agent_slug = "sgr"
        cli.current_thread_id = "thread-1"

        await cli._dispatch_command("leave")

        self.assertIsNone(cli.default_target_agent_slug)
        self.assertIsNone(cli.current_thread_id)

    async def test_start_autobinds_free_port_and_registers_actual_base_url(self) -> None:
        cli, client = self._cli()

        await cli.start()
        try:
            self.assertEqual(len(client.register_calls), 1)
            self.assertGreater(cli.listen_port, 0)
            self.assertIn(f":{cli.listen_port}", client.register_calls[0]["base_url"])
        finally:
            await cli.stop()


class OrchestraThreadsClientSurfaceTests(unittest.TestCase):
    def test_client_keeps_threads_default_url(self) -> None:
        client = OrchestraThreadsClient(base_url="http://127.0.0.1:8788")
        self.assertEqual(client.base_url, "http://127.0.0.1:8788")
