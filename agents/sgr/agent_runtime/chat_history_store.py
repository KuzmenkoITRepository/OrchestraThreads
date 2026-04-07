from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from agents.sgr.agent_runtime.chat_history import ChatTurn

logger = logging.getLogger(__name__)


def remove_persist_file(persist_dir: Path | None, session_key: str) -> None:
    if persist_dir is None:
        return
    session_path(persist_dir, session_key).unlink(missing_ok=True)


def session_path(persist_dir: Path, session_key: str) -> Path:
    safe_name = session_key.replace("/", "_").replace(":", "_")
    return persist_dir / f"{safe_name}.json"


def load_session_file(
    fpath: Path,
    max_turns: int,
) -> tuple[str, deque[ChatTurn]] | None:
    raw = load_file_payload(fpath)
    if raw is None:
        return None
    session_key = fpath.stem.replace("_", ":", 1)
    return session_key, build_session(raw, max_turns)


def load_file_payload(fpath: Path) -> list[object] | None:
    try:
        raw = json.loads(fpath.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to load chat history: %s", fpath)
        return None
    if isinstance(raw, list):
        return raw
    logger.warning("Ignoring invalid chat history payload: %s", fpath)
    return None


def build_session(raw: Iterable[object], max_turns: int) -> deque[ChatTurn]:
    session: deque[ChatTurn] = deque(maxlen=max_turns)
    entries = list(raw)[-max_turns:]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        session.append(
            ChatTurn(
                user_text=str(entry.get("user_text", "")),
                assistant_text=str(entry.get("assistant_text", "")),
            )
        )
    return session


def persist_session(
    persist_dir: Path | None,
    sessions: dict[str, deque[ChatTurn]],
    session_key: str,
) -> None:
    if persist_dir is None:
        return
    session = sessions.get(session_key)
    if not session:
        return
    fpath = session_path(persist_dir, session_key)
    turns = [asdict(turn) for turn in session]
    fpath.write_text(json.dumps(turns, ensure_ascii=False), encoding="utf-8")


def clear_persisted_sessions(persist_dir: Path | None) -> None:
    if persist_dir is None:
        return
    for fpath in persist_dir.glob("*.json"):
        fpath.unlink(missing_ok=True)
