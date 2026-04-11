from __future__ import annotations

import uuid
from dataclasses import dataclass

from core.telegram_bot_listener.json_types import JsonDict, optional_text, utc_now_iso
from core.telegram_bot_listener.models import ListenerState, SurveySession, TranscriptEntry


@dataclass(frozen=True, slots=True)
class AppendEntryRequest:
    telegram_user_id: int
    chat_id: int
    actor: str
    kind: str
    text: str
    structured: JsonDict
    session_id: str | None


@dataclass(frozen=True, slots=True)
class HistoryViewRequest:
    telegram_user_id: int
    session_id: str | None
    limit: int


class _HistoryFormatter:
    def timeline_entry(self, entry: TranscriptEntry) -> JsonDict:
        return {
            "ts": entry.timestamp,
            "actor": entry.actor,
            "kind": entry.kind,
            "text": entry.text,
            "session_id": optional_text(entry.session_id),
            "structured": entry.structured,
        }

    def survey_state(self, session: SurveySession | None) -> JsonDict:
        if session is None:
            return {}
        return {
            "session_id": session.session_id,
            "title": session.title,
            "status": session.status,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
            "answers": {key: list(values) for key, values in session.answers.items()},
            "questions": [question.to_dict() for question in session.questions],
        }

    def session_id(self, session: SurveySession | None) -> str | None:
        if session is None:
            return None
        return session.session_id


class HistoryStateOps:
    def __init__(self) -> None:
        self._formatter = _HistoryFormatter()

    def append_entry(self, state: ListenerState, request: AppendEntryRequest) -> None:
        state.transcript.append(
            TranscriptEntry(
                entry_id=uuid.uuid4().hex,
                session_id=request.session_id,
                telegram_user_id=request.telegram_user_id,
                chat_id=request.chat_id,
                timestamp=utc_now_iso(),
                actor=request.actor,
                kind=request.kind,
                text=request.text,
                structured=request.structured,
            )
        )

    def build_history_view(self, state: ListenerState, request: HistoryViewRequest) -> JsonDict:
        session = self._resolve_view_session(
            state,
            request.telegram_user_id,
            request.session_id,
        )
        entries = self._matching_entries(state, request.telegram_user_id, request.session_id)
        start_index = max(0, len(entries) - max(1, request.limit))
        timeline = [self._formatter.timeline_entry(entry) for entry in entries[start_index:]]
        return {
            "ok": True,
            "telegram_user_id": request.telegram_user_id,
            "session_id": self._formatter.session_id(session),
            "timeline": timeline,
            "survey_state": self._formatter.survey_state(session),
        }

    def _matching_entries(
        self,
        state: ListenerState,
        telegram_user_id: int,
        session_id: str | None,
    ) -> list[TranscriptEntry]:
        entries = [
            entry for entry in state.transcript if entry.telegram_user_id == telegram_user_id
        ]
        if session_id is None:
            return entries
        return [entry for entry in entries if entry.session_id == session_id]

    def _resolve_view_session(
        self,
        state: ListenerState,
        telegram_user_id: int,
        session_id: str | None,
    ) -> SurveySession | None:
        if session_id:
            return self._user_owned_session(state.sessions.get(session_id), telegram_user_id)
        return self._active_session(state, telegram_user_id)

    def _active_session(self, state: ListenerState, telegram_user_id: int) -> SurveySession | None:
        session_id = state.active_session_by_user.get(str(telegram_user_id))
        if session_id is None:
            return None
        return state.sessions.get(session_id)

    def _user_owned_session(
        self,
        session: SurveySession | None,
        telegram_user_id: int,
    ) -> SurveySession | None:
        if session is None:
            return None
        if session.telegram_user_id != telegram_user_id:
            return None
        return session


HISTORY_OPS = HistoryStateOps()
