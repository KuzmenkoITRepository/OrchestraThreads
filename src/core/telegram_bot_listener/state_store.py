from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, cast

from core.telegram_bot_listener.json_types import JsonDict, parse_int, utc_now_iso
from core.telegram_bot_listener.models import (
    ListenerState,
    SelectionResult,
    SurveyQuestion,
    SurveySession,
)

if TYPE_CHECKING:
    from typing import Protocol

    from core.telegram_bot_listener.state_store_parts.history import (
        AppendEntryRequest,
        HistoryStateOps,
        HistoryViewRequest,
    )
    from core.telegram_bot_listener.state_store_parts.persistence import PersistenceStateOps
    from core.telegram_bot_listener.state_store_parts.sessions import (
        SessionCreateRequest,
        SessionStateOps,
    )

    class _PersistentStore(Protocol):
        _state_file: Path
        _lock: asyncio.Lock
        _state: ListenerState

        async def _persist(self) -> None: ...

        async def _persist_locked(self) -> None: ...


class _StoreMutationApi:
    def __init__(self, store: TelegramBotStateStore) -> None:
        self._store = store
        self._session_ops = cast(
            "SessionStateOps",
            import_module("core.telegram_bot_listener.state_store_parts.sessions").SESSION_OPS,
        )
        self._history_ops = cast(
            "HistoryStateOps",
            import_module("core.telegram_bot_listener.state_store_parts.history").HISTORY_OPS,
        )
        self._session_create_request = cast(
            "type[SessionCreateRequest]",
            import_module(
                "core.telegram_bot_listener.state_store_parts.sessions"
            ).SessionCreateRequest,
        )
        self._append_entry_request = cast(
            "type[AppendEntryRequest]",
            import_module(
                "core.telegram_bot_listener.state_store_parts.history"
            ).AppendEntryRequest,
        )

    async def create_survey_session(self, **payload: object) -> SurveySession:
        async with self._store._lock:
            telegram_user_id = parse_int(payload["telegram_user_id"])
            self._session_ops.ensure_no_active_session(self._store._state, telegram_user_id)
            session = self._session_ops.create_session(
                self._session_create_request(
                    title=str(payload["title"]),
                    telegram_user_id=telegram_user_id,
                    chat_id=parse_int(payload["chat_id"]),
                    questions=cast(list[SurveyQuestion], payload["questions"]),
                )
            )
            self._store._state.sessions[session.session_id] = session
            self._store._state.active_session_by_user[str(telegram_user_id)] = session.session_id
            await self._store._persist_locked()
            return session

    async def record_outbound_message(self, **payload: object) -> None:
        async with self._store._lock:
            telegram_user_id = parse_int(payload["telegram_user_id"])
            session_id = cast(str | None, payload["session_id"])
            session = self._session_ops.session_for_append(
                self._store._state,
                telegram_user_id,
                session_id,
            )
            resolved_session_id = session_id
            if session is not None:
                session.outbound_message_ids.append(parse_int(payload["message_id"]))
                resolved_session_id = session.session_id
            self._history_ops.append_entry(
                self._store._state,
                self._append_entry_request(
                    telegram_user_id=telegram_user_id,
                    chat_id=parse_int(payload["chat_id"]),
                    actor="agent",
                    kind=str(payload["kind"]),
                    text=str(payload["text"]),
                    structured=cast(JsonDict, payload["structured"]),
                    session_id=resolved_session_id,
                ),
            )
            await self._store._persist_locked()

    async def record_text_message(self, **payload: object) -> str | None:
        async with self._store._lock:
            telegram_user_id = parse_int(payload["telegram_user_id"])
            session_id = self._store._state.active_session_by_user.get(str(telegram_user_id))
            self._history_ops.append_entry(
                self._store._state,
                self._append_entry_request(
                    telegram_user_id=telegram_user_id,
                    chat_id=parse_int(payload["chat_id"]),
                    actor="user",
                    kind=str(payload["kind"]),
                    text=str(payload["text"]),
                    structured={},
                    session_id=session_id,
                ),
            )
            await self._store._persist_locked()
            return session_id

    async def record_selection(self, **payload: object) -> SelectionResult | None:
        async with self._store._lock:
            telegram_user_id = parse_int(payload["telegram_user_id"])
            session = self._session_ops.active_session(self._store._state, telegram_user_id)
            if session is None:
                return None
            action = session.callback_actions.get(str(payload["callback_data"]))
            if action is None:
                return None
            answers = list(session.answers.get(action.question_id, []))
            selected = self._session_ops.merge_answer(
                answers,
                action.option_id,
                multi_select=action.multi_select,
            )
            session.answers[action.question_id] = answers
            self._history_ops.append_entry(
                self._store._state,
                self._append_entry_request(
                    telegram_user_id=telegram_user_id,
                    chat_id=parse_int(payload["chat_id"]),
                    actor="user",
                    kind="button_selection",
                    text=self._session_ops.selection_text(action.option_label, selected),
                    structured={
                        "question_id": action.question_id,
                        "option_id": action.option_id,
                        "selected": selected,
                    },
                    session_id=session.session_id,
                ),
            )
            await self._store._persist_locked()
            return SelectionResult(
                session_id=session.session_id,
                question_id=action.question_id,
                option_id=action.option_id,
                option_label=action.option_label,
                selected=selected,
            )

    async def finish_active_session(self, **payload: object) -> SurveySession | None:
        async with self._store._lock:
            telegram_user_id = parse_int(payload["telegram_user_id"])
            session = self._session_ops.active_session(self._store._state, telegram_user_id)
            session_id = None if session is None else session.session_id
            self._history_ops.append_entry(
                self._store._state,
                self._append_entry_request(
                    telegram_user_id=telegram_user_id,
                    chat_id=parse_int(payload["chat_id"]),
                    actor="user",
                    kind="command",
                    text=str(payload["command_text"]),
                    structured={},
                    session_id=session_id,
                ),
            )
            if session is None:
                await self._store._persist_locked()
                return None
            session.status = "completed"
            session.completed_at = utc_now_iso()
            self._store._state.active_session_by_user.pop(str(telegram_user_id), None)
            await self._store._persist_locked()
            return session


class _StoreReadApi:
    def __init__(self, store: TelegramBotStateStore) -> None:
        self._store = store
        self._history_ops = cast(
            "HistoryStateOps",
            import_module("core.telegram_bot_listener.state_store_parts.history").HISTORY_OPS,
        )
        self._history_view_request = cast(
            "type[HistoryViewRequest]",
            import_module(
                "core.telegram_bot_listener.state_store_parts.history"
            ).HistoryViewRequest,
        )

    async def history_view(self, **payload: object) -> JsonDict:
        async with self._store._lock:
            return self._history_ops.build_history_view(
                self._store._state,
                self._history_view_request(
                    telegram_user_id=parse_int(payload["telegram_user_id"]),
                    session_id=cast(str | None, payload["session_id"]),
                    limit=parse_int(payload["limit"]),
                ),
            )

    async def session_by_id(self, session_id: str) -> SurveySession | None:
        async with self._store._lock:
            return self._store._state.sessions.get(session_id)


class _StorePersistenceMixin:
    async def start(self) -> None:
        store = cast("_PersistentStore", self)
        if not store._state_file.exists():
            await store._persist()
            return
        persistence = cast(
            "PersistenceStateOps",
            import_module(
                "core.telegram_bot_listener.state_store_parts.persistence"
            ).PERSISTENCE_OPS,
        )
        store._state = persistence.load_state(store._state_file)

    async def close(self) -> None:
        store = cast("_PersistentStore", self)
        await store._persist()

    async def set_last_update_id(self, update_id: int) -> None:
        store = cast("_PersistentStore", self)
        async with store._lock:
            store._state.last_update_id = max(store._state.last_update_id, int(update_id))
            await store._persist_locked()

    async def last_update_id(self) -> int:
        store = cast("_PersistentStore", self)
        async with store._lock:
            return store._state.last_update_id

    async def _persist(self) -> None:
        store = cast("_PersistentStore", self)
        async with store._lock:
            await store._persist_locked()

    async def _persist_locked(self) -> None:
        store = cast("_PersistentStore", self)
        persistence = cast(
            "PersistenceStateOps",
            import_module(
                "core.telegram_bot_listener.state_store_parts.persistence"
            ).PERSISTENCE_OPS,
        )
        persistence.persist_state(store._state_file, store._state)


class TelegramBotStateStore(_StorePersistenceMixin):
    create_survey_session: Callable[..., Awaitable[SurveySession]]
    record_outbound_message: Callable[..., Awaitable[None]]
    record_text_message: Callable[..., Awaitable[str | None]]
    record_selection: Callable[..., Awaitable[SelectionResult | None]]
    finish_active_session: Callable[..., Awaitable[SurveySession | None]]

    def __init__(self, state_file: str) -> None:
        self._state_file = Path(state_file)
        self._lock = asyncio.Lock()
        self._state = ListenerState()
        self._mutation_api = _StoreMutationApi(self)
        self._read_api = _StoreReadApi(self)
        self.create_survey_session = self._mutation_api.create_survey_session
        self.record_outbound_message = self._mutation_api.record_outbound_message
        self.record_text_message = self._mutation_api.record_text_message
        self.record_selection = self._mutation_api.record_selection
        self.finish_active_session = self._mutation_api.finish_active_session

    async def history_view(
        self,
        *,
        telegram_user_id: int,
        session_id: str | None,
        limit: int,
    ) -> JsonDict:
        return await self._read_api.history_view(
            telegram_user_id=telegram_user_id,
            session_id=session_id,
            limit=limit,
        )

    async def session_by_id(self, session_id: str) -> SurveySession | None:
        return await self._read_api.session_by_id(session_id)
