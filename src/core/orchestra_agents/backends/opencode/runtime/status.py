from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.opencode.runtime.state import (
    Components,
    DispatchState,
)


def build_status_extras(
    components: Components,
    serve_port: int,
    dispatch: DispatchState,
) -> dict[str, Any]:
    process_running = bool(components.process and components.process.is_alive())
    manager = components.session_manager
    active_session_id = None if manager is None else manager.active_session_id
    return {
        "wrapper_mode": "opencode_omo",
        "opencode_process_running": process_running,
        "opencode_serve_port": serve_port,
        "last_dispatch_model": _extract_model(dispatch.last_result),
        "last_dispatch_tokens": _extract_tokens(dispatch.last_result),
        "active_session_id": active_session_id,
    }


def _extract_model(payload: dict[str, Any]) -> str | None:
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    model_id = str(info.get("modelID") or "").strip()
    return model_id or None


def _extract_tokens(payload: dict[str, Any]) -> dict[str, int]:
    raw_tokens = _raw_tokens(payload)
    if not isinstance(raw_tokens, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("total", "input", "output"):
        parsed_value = _parse_token(raw_tokens.get(key))
        if parsed_value is not None:
            result[key] = parsed_value
    return result


def _raw_tokens(payload: dict[str, Any]) -> object:
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    return info.get("tokens")


def _parse_token(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
