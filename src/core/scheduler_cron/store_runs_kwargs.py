from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompleteRunValues:
    result_payload: dict[str, object] | None
    error_message: str | None
    duration_ms: int | None


def parse_complete_run_kwargs(
    kwargs: dict[str, object],
) -> CompleteRunValues:
    payload = dict(kwargs)
    run_result = _run_result(payload)
    error_message = _optional_string(payload, "error_message")
    duration_ms = _optional_int(payload, "duration_ms")
    _ensure_no_unknown_kwargs(payload)
    return CompleteRunValues(
        result_payload=run_result,
        error_message=error_message,
        duration_ms=duration_ms,
    )


def _run_result(payload: dict[str, object]) -> dict[str, object] | None:
    result_value = payload.pop("result", None)
    override_value = payload.pop("run_result", None)
    field_value = result_value if override_value is None else override_value
    if field_value is None:
        return None
    if isinstance(field_value, dict):
        return field_value
    raise TypeError("complete_run() result must be dict[str, object] | None")


def _optional_string(payload: dict[str, object], field_name: str) -> str | None:
    field_value = payload.pop(field_name, None)
    if field_value is None or isinstance(field_value, str):
        return field_value
    raise TypeError(f"complete_run() {field_name} must be str | None")


def _optional_int(payload: dict[str, object], field_name: str) -> int | None:
    field_value = payload.pop(field_name, None)
    if field_value is None or isinstance(field_value, int):
        return field_value
    raise TypeError(f"complete_run() {field_name} must be int | None")


def _ensure_no_unknown_kwargs(payload: dict[str, object]) -> None:
    if not payload:
        return
    unknown = ", ".join(sorted(payload))
    raise TypeError(f"complete_run() got unexpected keyword arguments: {unknown}")
