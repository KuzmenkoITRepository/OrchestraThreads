"""Session chat history — stores user/assistant message pairs per session."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from core.orchestra_agents.backends.sgr.chat_history_store import (
    clear_persisted_sessions as _clear_persisted_sessions,
)
from core.orchestra_agents.backends.sgr.chat_history_store import (
    load_session_file as _load_session_file,
)
from core.orchestra_agents.backends.sgr.chat_history_store import (
    persist_session as _persist_session,
)
from core.orchestra_agents.backends.sgr.chat_history_store import (
    remove_persist_file as _remove_persist_file,
)

_DEFAULT_MAX_TURNS = 20


@dataclass(frozen=True)
class ChatTurn:
    """One turn of conversation: user message + assistant reply."""

    user_text: str
    assistant_text: str


class SessionChatHistory:
    """Stores chat turns per session key for multi-turn LLM context."""

    def __init__(
        self,
        max_turns: int = _DEFAULT_MAX_TURNS,
        persist_dir: str | None = None,
    ) -> None:
        self._sessions: dict[str, deque[ChatTurn]] = {}
        self._max_turns = max_turns
        self._persist_dir = Path(persist_dir) if persist_dir else None
        if self._persist_dir is not None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_all()

    def record_turn(
        self,
        *,
        session_key: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        """Record a completed turn (user message + assistant reply)."""
        user_clean = " ".join(user_text.split()).strip()
        assistant_clean = " ".join(assistant_text.split()).strip()
        if not user_clean:
            return
        if not assistant_clean:
            assistant_clean = "(no reply)"
        session = self._get_or_create(session_key)
        session.append(ChatTurn(user_text=user_clean, assistant_text=assistant_clean))
        _persist_session(self._persist_dir, self._sessions, session_key)

    def messages_for_session(self, session_key: str) -> list[dict[str, str]]:
        """Return chat history as OpenAI-format messages list."""
        session = self._sessions.get(session_key)
        if not session:
            return []
        messages: list[dict[str, str]] = []
        for turn in session:
            messages.append({"role": "user", "content": turn.user_text})
            messages.append({"role": "assistant", "content": turn.assistant_text})
        return messages

    def clear(self) -> None:
        """Clear all sessions and remove persisted files."""
        self._sessions.clear()
        _clear_persisted_sessions(self._persist_dir)

    def clear_session(self, session_key: str) -> None:
        """Clear a specific session."""
        self._sessions.pop(session_key, None)
        _remove_persist_file(self._persist_dir, session_key)

    def _get_or_create(self, session_key: str) -> deque[ChatTurn]:
        session = self._sessions.get(session_key)
        if session is None:
            session = deque(maxlen=self._max_turns)
            self._sessions[session_key] = session
        return session

    def _load_all(self) -> None:
        if self._persist_dir is None:
            return
        for fpath in self._persist_dir.glob("*.json"):
            loaded_session = _load_session_file(fpath, self._max_turns)
            if loaded_session is None:
                continue
            self._sessions[loaded_session[0]] = loaded_session[1]
