from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiohttp import web

from core.telegram_bot_listener import http_payloads, http_send_ops
from core.telegram_bot_listener.bot_api import extract_message_id
from core.telegram_bot_listener.json_types import cast_json_dict
from core.telegram_bot_listener.models import SurveyQuestion, SurveySession

if TYPE_CHECKING:
    from core.telegram_bot_listener.service import TelegramBotListenerService


@dataclass(frozen=True)
class TelegramBotHttpHandlers:
    service: TelegramBotListenerService

    async def healthz(self, _: web.Request) -> web.Response:
        status = 200 if await self.service.is_healthy() else 503
        return web.json_response({"status": "ok" if status == 200 else "error"}, status=status)

    async def send_message(self, request: web.Request) -> web.Response:
        _require_api_token(request, self.service.config.api_token)
        payload = cast_json_dict(await request.json())
        telegram_user_id = http_payloads.required_user_id(payload)
        _require_allowed_user(telegram_user_id, self.service.config.allowed_user_ids)
        text = http_payloads.required_text(payload, field_name="text")
        response = await self.service.bot_api.send_message(chat_id=telegram_user_id, text=text)
        message_id = extract_message_id(response)
        await self.service.store.record_outbound_message(
            telegram_user_id=telegram_user_id,
            chat_id=telegram_user_id,
            text=text,
            kind="message",
            structured={},
            session_id=None,
            message_id=message_id,
        )
        return web.json_response(
            {"ok": True, "message_id": message_id, "telegram_user_id": telegram_user_id}
        )

    async def send_buttons(self, request: web.Request) -> web.Response:
        _require_api_token(request, self.service.config.api_token)
        payload = cast_json_dict(await request.json())
        telegram_user_id = http_payloads.required_user_id(payload)
        _require_allowed_user(telegram_user_id, self.service.config.allowed_user_ids)
        text = http_payloads.required_text(payload, field_name="text")
        buttons = http_payloads.parse_buttons(payload)
        message_id = await http_send_ops.send_button_message(
            service=self.service,
            telegram_user_id=telegram_user_id,
            text=text,
            buttons=buttons,
        )
        await self.service.store.record_outbound_message(
            telegram_user_id=telegram_user_id,
            chat_id=telegram_user_id,
            text=text,
            kind="buttons",
            structured={"buttons": http_payloads.json_buttons(buttons)},
            session_id=None,
            message_id=message_id,
        )
        return web.json_response(
            {"ok": True, "message_id": message_id, "telegram_user_id": telegram_user_id}
        )

    async def create_survey(self, request: web.Request) -> web.Response:
        _require_api_token(request, self.service.config.api_token)
        payload = cast_json_dict(await request.json())
        telegram_user_id = http_payloads.required_user_id(payload)
        _require_allowed_user(telegram_user_id, self.service.config.allowed_user_ids)
        title = http_payloads.required_text(payload, field_name="title")
        questions = http_payloads.parse_questions(payload)
        session = await self.service.store.create_survey_session(
            title=title,
            telegram_user_id=telegram_user_id,
            chat_id=telegram_user_id,
            questions=questions,
        )
        await self._send_survey_messages(
            telegram_user_id, session.session_id, title, questions, session
        )
        return web.json_response(
            {
                "ok": True,
                "session_id": session.session_id,
                "telegram_user_id": telegram_user_id,
                "question_count": len(questions),
            }
        )

    async def history(self, request: web.Request) -> web.Response:
        _require_api_token(request, self.service.config.api_token)
        telegram_user_id, session_id, limit = http_payloads.history_request(request)
        _require_allowed_user(telegram_user_id, self.service.config.allowed_user_ids)
        return web.json_response(
            await self.service.store.history_view(
                telegram_user_id=telegram_user_id,
                session_id=session_id,
                limit=limit,
            )
        )

    async def _send_survey_messages(
        self,
        telegram_user_id: int,
        session_id: str,
        title: str,
        questions: list[SurveyQuestion],
        session: SurveySession,
    ) -> None:
        intro_text = f"{title}\n\nUse /done when you finish the survey."
        intro_response = await self.service.bot_api.send_message(
            chat_id=telegram_user_id,
            text=intro_text,
        )
        await self.service.store.record_outbound_message(
            telegram_user_id=telegram_user_id,
            chat_id=telegram_user_id,
            text=intro_text,
            kind="survey_intro",
            structured={},
            session_id=session_id,
            message_id=extract_message_id(intro_response),
        )
        await http_send_ops.send_question_messages(
            service=self.service,
            session=session,
            session_id=session_id,
            telegram_user_id=telegram_user_id,
            questions=questions,
        )


def _require_allowed_user(
    telegram_user_id: int,
    allowed_user_ids: frozenset[int],
) -> None:
    if telegram_user_id in allowed_user_ids:
        return
    raise web.HTTPForbidden(reason=f"telegram_user_id {telegram_user_id} is not allowed")


def _require_api_token(request: web.Request, expected_token: str) -> None:
    token = str(request.headers.get("X-Telegram-Bot-Listener-Token") or "").strip()
    if token == expected_token:
        return
    raise web.HTTPUnauthorized(reason="missing or invalid listener api token")
