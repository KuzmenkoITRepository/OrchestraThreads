from __future__ import annotations

from datetime import datetime

from core.scheduler_cron import common as scheduler_common


def create_job_args(kwargs: dict[str, object]) -> list[object]:
    return _CreateJobPayload.from_kwargs(kwargs).as_args()


def _validate_kwargs(
    kwargs: dict[str, object],
    *,
    required_keys: set[str],
    default_values: dict[str, object],
) -> None:
    allowed_keys = required_keys | set(default_values)
    unknown = sorted(set(kwargs) - allowed_keys)
    if unknown:
        unknown_text = ", ".join(unknown)
        raise TypeError(f"create_job() got unexpected keyword arguments: {unknown_text}")
    missing = sorted(required_keys - set(kwargs))
    if missing:
        missing_text = ", ".join(missing)
        raise TypeError(f"create_job() missing required keyword-only arguments: {missing_text}")


def _required(payload: dict[str, object], key: str, expected_type: type[object]) -> object:
    field_value = payload.get(key)
    if isinstance(field_value, expected_type):
        return field_value
    expected_name = expected_type.__name__
    raise TypeError(f"create_job() {key} must be {expected_name}")


class _CreateJobPayload:
    _required_keys = {
        "name",
        "job_type",
        "schedule",
        "action_type",
        "action_payload",
        "created_by",
    }
    _default_values = {
        "enabled": True,
        "auto_delete": False,
        "misfire_policy": "skip",
        "metadata": None,
        "last_run_at": None,
        "next_run_at": None,
    }

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    @classmethod
    def from_kwargs(cls, kwargs: dict[str, object]) -> _CreateJobPayload:
        _validate_kwargs(
            kwargs,
            required_keys=cls._required_keys,
            default_values=cls._default_values,
        )
        payload = dict(cls._default_values)
        payload.update(kwargs)
        return cls(payload)

    def as_args(self) -> list[object]:
        payload = self._payload
        return [
            str(_required(payload, "name", str)).strip(),
            self._choice("job_type", scheduler_common.JOB_TYPES),
            str(_required(payload, "schedule", str)).strip(),
            self._choice("action_type", scheduler_common.ACTION_TYPES),
            self._optional("action_payload", dict) or {},
            _required(payload, "enabled", bool),
            _required(payload, "auto_delete", bool),
            self._choice("misfire_policy", scheduler_common.MISFIRE_POLICIES),
            str(_required(payload, "created_by", str)).strip(),
            self._optional("metadata", dict) or {},
            self._optional("last_run_at", datetime),
            self._optional("next_run_at", datetime),
        ]

    def _choice(self, key: str, allowed: tuple[str, ...]) -> str:
        text_value = self._required_text(key)
        return scheduler_common.ensure_choice(text_value, field=key, allowed=allowed)

    def _required_text(self, key: str) -> str:
        field_value = self._payload.get(key)
        if isinstance(field_value, str):
            return field_value
        raise TypeError(f"create_job() {key} must be str")

    def _optional(
        self,
        key: str,
        expected_type: type[object],
    ) -> object | None:
        field_value = self._payload.get(key)
        if field_value is None:
            return None
        if isinstance(field_value, expected_type):
            return field_value
        expected_name = expected_type.__name__
        raise TypeError(f"create_job() {key} must be {expected_name} | None")
