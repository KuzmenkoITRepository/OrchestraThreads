"""Mapping between ``context_id`` and opencode session IDs with file persistence."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.orchestra_agents.templates.opencode.agent_runtime.opencode_client import (
        OpencodeClient,
    )


class SessionManager:
    """Track which opencode session belongs to the current ``context_id``."""

    def __init__(self, state_dir: Path, client: OpencodeClient) -> None:
        self._state_dir = state_dir
        self._client = client
        self._map_path = state_dir / "session_map.json"
        self._lock = asyncio.Lock()
        self._context_id: str | None = None
        self._session_id: str | None = None

    @property
    def active_session_id(self) -> str | None:
        return self._session_id

    async def get_or_create_session(self, context_id: str) -> str:
        async with self._lock:
            if self._context_id == context_id and self._session_id:
                return self._session_id
            response = await self._client.create_session()
            session_id = _require_session_id(response)
            self._context_id = context_id
            self._session_id = session_id
            _persist_mapping(self._map_path, context_id, session_id)
            return session_id

    async def delete_session(self, context_id: str) -> None:
        async with self._lock:
            if self._context_id == context_id and self._session_id:
                await self._client.delete_session(self._session_id)
            self._context_id = None
            self._session_id = None
            _remove_mapping_file(self._map_path)

    async def restore(self) -> None:
        async with self._lock:
            stored = _read_mapping_file(self._map_path)
            context_id = _opt_str(stored, "context_id")
            session_id = _opt_str(stored, "opencode_session_id")
            if not context_id or not session_id:
                _remove_mapping_file(self._map_path)
                return
            if not await self._session_exists(session_id):
                _remove_mapping_file(self._map_path)
                return
            self._context_id = context_id
            self._session_id = session_id

    async def _session_exists(self, session_id: str) -> bool:
        sessions = await self._client.list_sessions()
        valid_sessions = [session for session in sessions if isinstance(session, dict)]
        session_ids = [str(session.get("id") or "") for session in valid_sessions]
        ids = set(session_ids)
        return session_id in ids


# ── helpers ────────────────────────────────────────────────────


def _require_session_id(response: dict[str, Any]) -> str:
    session_id = str(response.get("id") or "").strip()
    if not session_id:
        raise RuntimeError("opencode create_session response missing id")
    return session_id


def _opt_str(payload: dict[str, Any], key: str) -> str | None:
    raw = str(payload.get(key) or "").strip()
    return raw or None


def _persist_mapping(path: Path, context_id: str, session_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "context_id": context_id,
        "opencode_session_id": session_id,
        "created_at": _utc_now_iso(),
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def _remove_mapping_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _read_mapping_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _utc_now_iso() -> str:
    now_utc = datetime.now(tz=UTC)
    without_microseconds = now_utc.replace(microsecond=0)
    iso_value = without_microseconds.isoformat()
    return iso_value.replace("+00:00", "Z")
