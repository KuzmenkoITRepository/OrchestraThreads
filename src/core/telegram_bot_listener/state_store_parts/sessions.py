from __future__ import annotations

import uuid
from dataclasses import dataclass

from core.telegram_bot_listener.json_types import JsonDict, utc_now_iso
from core.telegram_bot_listener.models import ListenerState, SurveyQuestion, SurveySession


@dataclass(frozen=True, slots=True)
class SessionCreateRequest:
    title: str
    telegram_user_id: int
    chat_id: int
    questions: list[SurveyQuestion]


class _CallbackActionFactory:
    def build(self, session_id: str, questions: list[SurveyQuestion]) -> JsonDict:
        callback_actions: JsonDict = {}
        for question in questions:
            callback_actions.update(self._question_actions(session_id, question))
        return callback_actions

    def _question_actions(self, session_id: str, question: SurveyQuestion) -> JsonDict:
        return {
            uuid.uuid4().hex[:12]: {
                "session_id": session_id,
                "question_id": question.question_id,
                "option_id": option.option_id,
                "option_label": option.label,
                "multi_select": question.multi_select,
            }
            for option in question.options
        }


class SessionStateOps:
    def ensure_no_active_session(self, state: ListenerState, telegram_user_id: int) -> None:
        if str(telegram_user_id) in state.active_session_by_user:
            raise ValueError("An active survey session already exists for this user")

    def create_session(self, request: SessionCreateRequest) -> SurveySession:
        session_id = uuid.uuid4().hex
        return SurveySession.from_dict(
            {
                "session_id": session_id,
                "title": request.title,
                "telegram_user_id": request.telegram_user_id,
                "chat_id": request.chat_id,
                "status": "active",
                "created_at": utc_now_iso(),
                "completed_at": None,
                "questions": [question.to_dict() for question in request.questions],
                "answers": {},
                "callback_actions": CALLBACK_ACTION_FACTORY.build(session_id, request.questions),
                "outbound_message_ids": [],
            }
        )

    def active_session(self, state: ListenerState, telegram_user_id: int) -> SurveySession | None:
        session_id = state.active_session_by_user.get(str(telegram_user_id))
        if session_id is None:
            return None
        return state.sessions.get(session_id)

    def session_for_append(
        self,
        state: ListenerState,
        telegram_user_id: int,
        session_id: str | None,
    ) -> SurveySession | None:
        if session_id:
            return state.sessions.get(session_id)
        return self.active_session(state, telegram_user_id)

    def merge_answer(self, answers: list[str], option_id: str, *, multi_select: bool) -> bool:
        if multi_select:
            return self._merge_multi_select_answer(answers, option_id)
        answers.clear()
        answers.append(option_id)
        return True

    def selection_text(self, option_label: str, selected: bool) -> str:
        if selected:
            return f"Selected: {option_label}"
        return f"Removed: {option_label}"

    def _merge_multi_select_answer(self, answers: list[str], option_id: str) -> bool:
        if option_id in answers:
            answers.remove(option_id)
            return False
        answers.append(option_id)
        return True


CALLBACK_ACTION_FACTORY = _CallbackActionFactory()
SESSION_OPS = SessionStateOps()
