from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from core.telegram_bot_listener.json_types import (
    JsonDict,
    cast_json_dict,
    optional_text,
    utc_now_iso,
)
from core.telegram_bot_listener.models import (
    ListenerState,
    SelectionResult,
    SurveyQuestion,
    SurveySession,
    TranscriptEntry,
)


class TelegramBotStateStore:  # noqa: WPS214 - File-backed state transitions are intentionally centralized here.
    def __init__(self, state_file: str) -> None:
        self._state_file = Path(state_file)
        self._lock = asyncio.Lock()
        self._state = ListenerState()

    async def start(self) -> None:
        if not self._state_file.exists():
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            await self._persist()
            return
        payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        self._state = ListenerState.from_dict(cast_json_dict(payload))

    async def close(self) -> None:
        await self._persist()

    async def set_last_update_id(self, update_id: int) -> None:
        async with self._lock:
            self._state.last_update_id = max(self._state.last_update_id, int(update_id))
            await self._persist_locked()

    async def last_update_id(self) -> int:
        async with self._lock:
            return self._state.last_update_id

    async def create_survey_session(
        self,
        *,
        title: str,
        telegram_user_id: int,
        chat_id: int,
        questions: list[SurveyQuestion],
    ) -> SurveySession:
        async with self._lock:
            self._ensure_no_active_session(telegram_user_id)
            session = self._new_session(
                title=title,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                questions=questions,
            )
            self._state.sessions[session.session_id] = session
            self._state.active_session_by_user[str(telegram_user_id)] = session.session_id
            await self._persist_locked()
            return session

    async def record_outbound_message(  # noqa: WPS211 - Transport writes need explicit event fields.
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        text: str,
        kind: str,
        structured: JsonDict,
        session_id: str | None,
        message_id: int,
    ) -> None:
        async with self._lock:
            session = self._session_for_append(telegram_user_id, session_id)
            if session is None:
                resolved_session_id = session_id
            else:
                session.outbound_message_ids.append(message_id)
                resolved_session_id = session.session_id
            self._append_entry(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                actor="agent",
                kind=kind,
                text=text,
                structured=structured,
                session_id=resolved_session_id,
            )
            await self._persist_locked()

    async def record_text_message(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        text: str,
        kind: str,
    ) -> str | None:
        async with self._lock:
            session_id = self._state.active_session_by_user.get(str(telegram_user_id))
            self._append_entry(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                actor="user",
                kind=kind,
                text=text,
                structured={},
                session_id=session_id,
            )
            await self._persist_locked()
            return session_id

    async def record_selection(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        callback_data: str,
    ) -> SelectionResult | None:
        async with self._lock:
            session = self._active_session(telegram_user_id)
            if session is None:
                return None
            action = session.callback_actions.get(callback_data)
            if action is None:
                return None
            answers = list(session.answers.get(action.question_id, []))
            selected = self._merge_answer(
                answers, action.option_id, multi_select=action.multi_select
            )
            session.answers[action.question_id] = answers
            text = self._selection_text(action.option_label, selected)
            self._append_entry(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                actor="user",
                kind="button_selection",
                text=text,
                structured={
                    "question_id": action.question_id,
                    "option_id": action.option_id,
                    "selected": selected,
                },
                session_id=session.session_id,
            )
            await self._persist_locked()
            return SelectionResult(
                session_id=session.session_id,
                question_id=action.question_id,
                option_id=action.option_id,
                option_label=action.option_label,
                selected=selected,
            )

    async def finish_active_session(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        command_text: str,
    ) -> SurveySession | None:
        async with self._lock:
            session = self._active_session(telegram_user_id)
            session_id = None if session is None else session.session_id
            self._append_entry(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                actor="user",
                kind="command",
                text=command_text,
                structured={},
                session_id=session_id,
            )
            if session is None:
                await self._persist_locked()
                return None
            session.status = "completed"
            session.completed_at = utc_now_iso()
            self._state.active_session_by_user.pop(str(telegram_user_id), None)
            await self._persist_locked()
            return session

    async def history_view(
        self,
        *,
        telegram_user_id: int,
        session_id: str | None,
        limit: int,
    ) -> JsonDict:
        async with self._lock:
            items = self._matching_entries(telegram_user_id, session_id)
            max_items = max(1, limit)
            sliced = _last_items(items, max_items)
            session = self._resolve_view_session(telegram_user_id, session_id)
            return {
                "ok": True,
                "telegram_user_id": telegram_user_id,
                "session_id": _session_id(session),
                "timeline": [self._timeline_entry(entry) for entry in sliced],
                "survey_state": self._survey_state(session),
            }

    async def session_by_id(self, session_id: str) -> SurveySession | None:
        async with self._lock:
            return self._state.sessions.get(session_id)

    def _ensure_no_active_session(self, telegram_user_id: int) -> None:
        if str(telegram_user_id) in self._state.active_session_by_user:
            raise ValueError("An active survey session already exists for this user")

    def _new_session(
        self,
        *,
        title: str,
        telegram_user_id: int,
        chat_id: int,
        questions: list[SurveyQuestion],
    ) -> SurveySession:
        session_id = uuid.uuid4().hex
        callback_actions = {}
        for question in questions:
            for option in question.options:
                token = uuid.uuid4().hex[:12]
                callback_actions[token] = {
                    "session_id": session_id,
                    "question_id": question.question_id,
                    "option_id": option.option_id,
                    "option_label": option.label,
                    "multi_select": question.multi_select,
                }
        return SurveySession.from_dict(
            {
                "session_id": session_id,
                "title": title,
                "telegram_user_id": telegram_user_id,
                "chat_id": chat_id,
                "status": "active",
                "created_at": utc_now_iso(),
                "completed_at": None,
                "questions": [survey_question.to_dict() for survey_question in questions],
                "answers": {},
                "callback_actions": callback_actions,
                "outbound_message_ids": [],
            }
        )

    def _active_session(self, telegram_user_id: int) -> SurveySession | None:
        session_id = self._state.active_session_by_user.get(str(telegram_user_id))
        if session_id is None:
            return None
        return self._state.sessions.get(session_id)

    def _session_for_append(
        self,
        telegram_user_id: int,
        session_id: str | None,
    ) -> SurveySession | None:
        if session_id:
            return self._state.sessions.get(session_id)
        return self._active_session(telegram_user_id)

    def _append_entry(  # noqa: WPS211 - Transcript entries store explicit transport fields.
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        actor: str,
        kind: str,
        text: str,
        structured: JsonDict,
        session_id: str | None,
    ) -> None:
        self._state.transcript.append(
            TranscriptEntry(
                entry_id=uuid.uuid4().hex,
                session_id=session_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                timestamp=utc_now_iso(),
                actor=actor,
                kind=kind,
                text=text,
                structured=structured,
            )
        )

    def _merge_answer(self, answers: list[str], option_id: str, *, multi_select: bool) -> bool:
        if multi_select:
            if option_id in answers:
                answers.remove(option_id)
                return False
            answers.append(option_id)
            return True
        answers.clear()
        answers.append(option_id)
        return True

    def _selection_text(self, option_label: str, selected: bool) -> str:
        if selected:
            return f"Selected: {option_label}"
        return f"Removed: {option_label}"

    def _matching_entries(
        self,
        telegram_user_id: int,
        session_id: str | None,
    ) -> list[TranscriptEntry]:
        entries = [
            entry for entry in self._state.transcript if entry.telegram_user_id == telegram_user_id
        ]
        if session_id is None:
            return entries
        return [entry for entry in entries if entry.session_id == session_id]

    def _resolve_view_session(
        self,
        telegram_user_id: int,
        session_id: str | None,
    ) -> SurveySession | None:
        if session_id:
            return _user_owned_session(self._state.sessions.get(session_id), telegram_user_id)
        return self._active_session(telegram_user_id)

    def _timeline_entry(self, entry: TranscriptEntry) -> JsonDict:
        return {
            "ts": entry.timestamp,
            "actor": entry.actor,
            "kind": entry.kind,
            "text": entry.text,
            "session_id": optional_text(entry.session_id),
            "structured": entry.structured,
        }

    def _survey_state(self, session: SurveySession | None) -> JsonDict:
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

    async def _persist(self) -> None:
        async with self._lock:
            await self._persist_locked()

    async def _persist_locked(self) -> None:
        payload = json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2)
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(payload, encoding="utf-8")


def _session_id(session: SurveySession | None) -> str | None:
    if session is None:
        return None
    return session.session_id


def _last_items(items: list[TranscriptEntry], max_items: int) -> list[TranscriptEntry]:
    start_index = max(0, len(items) - max_items)
    return items[start_index:]


def _user_owned_session(
    session: SurveySession | None,
    telegram_user_id: int,
) -> SurveySession | None:
    if session is None:
        return None
    if session.telegram_user_id != telegram_user_id:
        return None
    return session
