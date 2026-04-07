# flake8: noqa: WPS202
from __future__ import annotations

from collections.abc import Mapping

from aiohttp import web

from core.telegram_bot_listener.json_types import JsonDict, JsonValue, cast_json_dict
from core.telegram_bot_listener.models import (
    CallbackAction,
    SurveyOption,
    SurveyQuestion,
    SurveySession,
)


def required_user_id(payload: JsonDict) -> int:
    raw_user_id = payload.get("telegram_user_id")
    if not isinstance(raw_user_id, int):
        raise ValueError("telegram_user_id is required")
    return raw_user_id


def required_text(payload: JsonDict, *, field_name: str) -> str:
    text = str(payload.get(field_name) or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def parse_buttons(payload: JsonDict) -> list[list[JsonDict]]:
    raw_rows = payload.get("buttons")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("buttons is required")
    return [_button_row(raw_row) for raw_row in raw_rows]


def history_request(request: web.Request) -> tuple[int, str | None, int]:
    telegram_user_id = int(request.query["telegram_user_id"])
    session_id = _optional_text(request.query.get("session_id"))
    limit = int(request.query.get("limit", "200"))
    return telegram_user_id, session_id, limit


def parse_questions(payload: JsonDict) -> list[SurveyQuestion]:
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("questions is required")
    return [_question(cast_json_dict(question)) for question in raw_questions]


def json_buttons(buttons: list[list[JsonDict]]) -> list[JsonValue]:
    return [[dict(button) for button in row] for row in buttons]


def question_buttons(session: SurveySession, question_id: str) -> list[list[JsonDict]]:
    return [
        row
        for question in session.questions
        if question.question_id == question_id
        for row in _question_rows(session.callback_actions, question, question_id)
    ]


def _button_row(raw_row: object) -> list[JsonDict]:
    if not isinstance(raw_row, list) or not raw_row:
        raise ValueError("buttons rows must be non-empty arrays")
    return [_button(button) for button in raw_row]


def _button(raw_button: object) -> JsonDict:
    if not isinstance(raw_button, dict):
        raise ValueError("button entries must be objects")
    payload = cast_json_dict(raw_button)
    return {
        "text": required_text(payload, field_name="text"),
        "callback_data": required_text(payload, field_name="id"),
    }


def _question(payload: JsonDict) -> SurveyQuestion:
    raw_options = payload.get("options")
    if not isinstance(raw_options, list) or not raw_options:
        raise ValueError("question options are required")
    return SurveyQuestion(
        question_id=required_text(payload, field_name="question_id"),
        text=required_text(payload, field_name="text"),
        multi_select=bool(payload.get("multi_select", False)),
        options=[_option(cast_json_dict(option)) for option in raw_options],
    )


def _option(payload: JsonDict) -> SurveyOption:
    return SurveyOption(
        option_id=required_text(payload, field_name="id"),
        label=required_text(payload, field_name="label"),
    )


def _question_rows(
    callback_actions: Mapping[str, CallbackAction],
    question: SurveyQuestion,
    question_id: str,
) -> list[list[JsonDict]]:
    return [
        [
            {
                "text": option.label,
                "callback_data": _token(callback_actions, question_id, option.option_id),
            }
        ]
        for option in question.options
    ]


def _token(
    callback_actions: Mapping[str, CallbackAction],
    question_id: str,
    option_id: str,
) -> str:
    for token, action in callback_actions.items():
        if action.question_id == question_id and action.option_id == option_id:
            return token
    raise ValueError("callback token not found")


def _optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
