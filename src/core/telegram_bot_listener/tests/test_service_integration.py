from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unused_port

from core.telegram_bot_listener.service import (
    TelegramBotListenerConfig,
    TelegramBotListenerService,
    build_app,
)


class _FakeTelegramApi:
    def __init__(self) -> None:
        self._updates: list[dict[str, Any]] = []
        self._message_id = 100
        self.sent_messages: list[dict[str, Any]] = []
        self.answered_callbacks: list[dict[str, Any]] = []

    def queue_updates(self, updates: list[dict[str, Any]]) -> None:
        self._updates.extend(updates)

    async def handle(self, request: web.Request) -> web.Response:
        method = request.match_info["method"]
        try:
            payload = await request.json()
        except ConnectionResetError:
            return web.json_response({"ok": True, "result": []})
        if method == "getUpdates":
            offset = int(payload.get("offset", 0))
            ready = [item for item in self._updates if int(item["update_id"]) >= offset]
            self._updates = [item for item in self._updates if int(item["update_id"]) < offset]
            return web.json_response({"ok": True, "result": ready})
        if method == "sendMessage":
            self._message_id += 1
            item = dict(payload)
            item["message_id"] = self._message_id
            self.sent_messages.append(item)
            return web.json_response({"ok": True, "result": {"message_id": self._message_id}})
        if method == "answerCallbackQuery":
            self.answered_callbacks.append(dict(payload))
            return web.json_response({"ok": True, "result": True})
        return web.json_response({"ok": False, "description": method}, status=404)


class _FakeEventsEngine:
    def __init__(self) -> None:
        self.deliveries: list[dict[str, Any]] = []

    async def deliver(self, request: web.Request) -> web.Response:
        self.deliveries.append(await request.json())
        return web.json_response({"success": True})


class TelegramBotListenerIntegrationTests(AioHTTPTestCase):  # noqa: WPS214 - aiohttp fixture lifecycle needs a few helpers.
    api_token = "listener-test-token"

    async def get_application(self) -> web.Application:
        self.telegram_api = _FakeTelegramApi()
        self.events_engine = _FakeEventsEngine()

        self.bot_port = unused_port()
        self.events_port = unused_port()
        self._bot_runner = await self._start_fake_server(self._bot_app(), self.bot_port)
        self._events_runner = await self._start_fake_server(self._events_app(), self.events_port)

        self.state_dir = Path(tempfile.mkdtemp(prefix="telegram_bot_listener_"))
        config = TelegramBotListenerConfig(
            host="127.0.0.1",
            port=0,
            bot_token="test-token",
            allowed_user_ids=frozenset((42, 43)),
            api_token=self.api_token,
            events_engine_url=f"http://127.0.0.1:{self.events_port}",
            target_agent_slug="secretary",
            state_file=str(self.state_dir / "state.json"),
            poll_timeout_seconds=1,
            api_base_url=f"http://127.0.0.1:{self.bot_port}",
        )
        self.service = TelegramBotListenerService(config)
        await self.service.store.start()
        return build_app(self.service)

    async def asyncTearDown(self) -> None:
        await self.service.stop()
        await self._bot_runner.cleanup()
        await self._events_runner.cleanup()
        await super().asyncTearDown()

    async def test_create_survey_and_history(self) -> None:
        response = await self.client.request(
            "POST",
            "/api/v1/surveys",
            headers=self._headers(),
            json={
                "telegram_user_id": 42,
                "title": "Discussion quality",
                "questions": [
                    {
                        "question_id": "quality",
                        "text": "How was the discussion?",
                        "options": [
                            {"id": "good", "label": "Good"},
                            {"id": "bad", "label": "Bad"},
                        ],
                    }
                ],
            },
        )
        body = await response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["question_count"], 1)
        self.assertEqual(len(self.telegram_api.sent_messages), 2)

        history_response = await self.client.request(
            "GET",
            "/api/v1/history?telegram_user_id=42&limit=10",
            headers=self._headers(),
        )
        history_body = await history_response.json()
        self.assertEqual(history_body["survey_state"]["title"], "Discussion quality")
        self.assertEqual(len(history_body["timeline"]), 2)

    async def test_http_api_rejects_non_whitelisted_user(self) -> None:
        response = await self.client.request(
            "POST",
            "/api/v1/messages",
            headers=self._headers(),
            json={"telegram_user_id": 999, "text": "blocked"},
        )
        self.assertEqual(response.status, 403)

    async def test_http_api_requires_listener_token(self) -> None:
        response = await self.client.request(
            "POST",
            "/api/v1/messages",
            json={"telegram_user_id": 42, "text": "blocked"},
        )
        self.assertEqual(response.status, 401)

    async def test_history_hides_foreign_session_state(self) -> None:
        create_response = await self.client.request(
            "POST",
            "/api/v1/surveys",
            headers=self._headers(),
            json={
                "telegram_user_id": 42,
                "title": "Discussion quality",
                "questions": [
                    {
                        "question_id": "quality",
                        "text": "How was the discussion?",
                        "options": [{"id": "good", "label": "Good"}],
                    }
                ],
            },
        )
        session_id = (await create_response.json())["session_id"]
        history_response = await self.client.request(
            "GET",
            f"/api/v1/history?telegram_user_id=43&session_id={session_id}&limit=10",
            headers=self._headers(),
        )
        history_body = await history_response.json()
        self.assertEqual(history_response.status, 200)
        self.assertEqual(history_body["survey_state"], {})
        self.assertEqual(history_body["timeline"], [])

    async def test_done_command_publishes_completion_event(self) -> None:
        create_response = await self.client.request(
            "POST",
            "/api/v1/surveys",
            headers=self._headers(),
            json={
                "telegram_user_id": 42,
                "title": "Discussion quality",
                "questions": [
                    {
                        "question_id": "quality",
                        "text": "How was the discussion?",
                        "options": [{"id": "good", "label": "Good"}],
                    }
                ],
            },
        )
        session_id = (await create_response.json())["session_id"]
        session = await self.service.store.session_by_id(session_id)
        assert session is not None
        callback_token = next(iter(session.callback_actions))
        self.telegram_api.queue_updates(
            [
                {
                    "update_id": 1,
                    "callback_query": {
                        "id": "cb1",
                        "from": {"id": 42},
                        "data": callback_token,
                        "message": {"chat": {"id": 42, "type": "private"}},
                    },
                },
                {
                    "update_id": 2,
                    "message": {
                        "chat": {"id": 42, "type": "private"},
                        "from": {"id": 42},
                        "text": "/done",
                    },
                },
            ]
        )
        await self.service.start()
        await self._wait_for(lambda: len(self.events_engine.deliveries) == 1)
        delivery = self.events_engine.deliveries[0]
        event = delivery["event_data"]["events"][0]
        self.assertEqual(event["event_kind"], "telegram_bot_survey_finished")
        self.assertEqual(event["metadata"]["answers"], {"quality": ["good"]})
        self.assertEqual(self.telegram_api.answered_callbacks[0]["text"], "Selection saved")

    async def _start_fake_server(self, app: web.Application, port: int) -> web.AppRunner:
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="127.0.0.1", port=port)
        await site.start()
        return runner

    def _bot_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/bottest-token/{method}", self.telegram_api.handle)
        return app

    def _events_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/deliver", self.events_engine.deliver)
        return app

    async def _wait_for(self, predicate: Any, *, attempts: int = 50) -> None:  # noqa: WPS476 - Polling waits for async side effects.
        for _ in range(attempts):
            if predicate():
                return
            await asyncio.sleep(0)  # noqa: WPS476 - async polling helper
        raise AssertionError("Condition not satisfied in time")

    def _headers(self) -> dict[str, str]:
        return {"X-Telegram-Bot-Listener-Token": self.api_token}
