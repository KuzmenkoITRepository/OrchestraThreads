from __future__ import annotations

from pathlib import Path
from typing import Any

from core.orchestra_agents.agent_mux_runtime.json_store import read_json_object


class QueueEntryMatcher:
    @staticmethod
    def normalize_optional_text(value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @classmethod
    def normalize_fields(cls, fields: dict[str, str | None]) -> dict[str, str]:
        return {
            key: normalized
            for key, value in fields.items()
            for normalized in (cls.normalize_optional_text(value),)
            if normalized is not None
        }

    @staticmethod
    def payload_dict(payload: dict[str, Any]) -> dict[str, Any]:
        payload_candidate = payload.get("payload")
        if isinstance(payload_candidate, dict):
            return payload_candidate
        return {}

    @classmethod
    def matches_field(
        cls,
        payload: dict[str, Any],
        raw_payload: dict[str, Any],
        item: tuple[str, str],
    ) -> bool:
        key, expected = item
        raw_value = raw_payload.get(key) or payload.get(key) or ""
        return cls.normalize_optional_text(raw_value) == expected

    @classmethod
    def matches_fields(cls, path: Path, *, normalized: dict[str, str]) -> bool:
        payload = read_json_object(path)
        raw_payload = cls.payload_dict(payload)
        for item in normalized.items():
            if not cls.matches_field(payload, raw_payload, item):
                return False
        return True
