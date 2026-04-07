from __future__ import annotations

from typing import TYPE_CHECKING

from core.telegram_bot_listener.bot_api import build_inline_keyboard, extract_message_id
from core.telegram_bot_listener.http_payloads import question_buttons
from core.telegram_bot_listener.json_types import JsonDict
from core.telegram_bot_listener.models import SurveyQuestion, SurveySession

if TYPE_CHECKING:
    from core.telegram_bot_listener.service import TelegramBotListenerService


async def send_button_message(
    *,
    service: TelegramBotListenerService,
    telegram_user_id: int,
    text: str,
    buttons: list[list[JsonDict]],
) -> int:
    response = await service.bot_api.send_message(
        chat_id=telegram_user_id,
        text=text,
        reply_markup=build_inline_keyboard(buttons),
    )
    return extract_message_id(response)


async def send_question_messages(  # noqa: WPS476 - Survey questions must be sent in-order.
    *,
    service: TelegramBotListenerService,
    session: SurveySession,
    session_id: str,
    telegram_user_id: int,
    questions: list[SurveyQuestion],
) -> None:
    for question in questions:
        message_id = await _send_question_message(  # noqa: WPS476 - Ordered chat delivery is required.
            service=service,
            telegram_user_id=telegram_user_id,
            question=question,
            session=session,
        )
        await service.store.record_outbound_message(  # noqa: WPS476 - Transcript order matches send order.
            telegram_user_id=telegram_user_id,
            chat_id=telegram_user_id,
            text=question.text,
            kind="survey_question",
            structured={"question_id": question.question_id},
            session_id=session_id,
            message_id=message_id,
        )


async def _send_question_message(
    *,
    service: TelegramBotListenerService,
    telegram_user_id: int,
    question: SurveyQuestion,
    session: SurveySession,
) -> int:
    response = await service.bot_api.send_message(
        chat_id=telegram_user_id,
        text=question.text,
        reply_markup=build_inline_keyboard(question_buttons(session, question.question_id)),
    )
    return extract_message_id(response)
