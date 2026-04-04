from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CODEX_PROVIDER = "openai-codex"
RUNTIME_STATE_VERSION = 1
RUNTIME_STATE_FILE_MODE = 0o644
RUNTIME_STATE_LOCK_MODE = 0o666


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def format_expires_at(expires_ms: int | None) -> str | None:
    if not isinstance(expires_ms, int):
        return None
    return datetime.fromtimestamp(expires_ms / 1000, tz=UTC).isoformat()


def mask_account_id(account_id: str | None) -> str:
    if not account_id:
        return "-"
    normalized = account_id.strip()
    if len(normalized) <= 10:
        return normalized
    return f"{normalized[:6]}...{normalized[-4:]}"


def _write_json(path: Path, payload: dict[str, Any], *, file_mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp_path, file_mode)
    os.replace(temp_path, path)
    os.chmod(path, file_mode)


def _load_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def _mutate_json(
    path: Path,
    *,
    default: dict[str, Any],
    update: Callable[[dict[str, Any]], Any],
    file_mode: int = 0o600,
    lock_mode: int | None = None,
    recover_read_errors: bool = False,
) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    result: dict[str, Any] = {}
    effective_lock_mode = lock_mode if lock_mode is not None else file_mode
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, effective_lock_mode)
    os.chmod(lock_path, effective_lock_mode)
    with os.fdopen(lock_fd, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            payload = _load_json(path, default=default)
        except (OSError, ValueError, TypeError, RuntimeError):
            if not recover_read_errors:
                raise
            payload = json.loads(json.dumps(default))
        updated = update(payload)
        if isinstance(updated, dict):
            payload = updated
        result["value"] = payload
        _write_json(path, payload, file_mode=file_mode)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return result.get("value")


def load_auth_store(path: Path) -> dict[str, Any]:
    data = _load_json(path, default={"version": 1, "profiles": {}, "order": {}})
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise RuntimeError(f'Invalid "profiles" object in {path}')
    order = data.get("order")
    if not isinstance(order, dict):
        raise RuntimeError(f'Invalid "order" object in {path}')
    return data


def _provider_order(data: dict[str, Any], provider: str) -> list[str]:
    order = data.get("order")
    if not isinstance(order, dict):
        return []
    values = order.get(provider)
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value.strip()]


def ordered_codex_profile_ids(data: dict[str, Any]) -> list[str]:
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return []
    ordered: list[str] = []
    for profile_id in _provider_order(data, CODEX_PROVIDER):
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            continue
        if profile.get("provider") != CODEX_PROVIDER or profile.get("type") != "oauth":
            continue
        if profile_id not in ordered:
            ordered.append(profile_id)
    for profile_id, profile in profiles.items():
        if not isinstance(profile_id, str) or not isinstance(profile, dict):
            continue
        if profile.get("provider") != CODEX_PROVIDER or profile.get("type") != "oauth":
            continue
        if profile_id not in ordered:
            ordered.append(profile_id)
    return ordered


def list_codex_profiles(path: Path) -> list[dict[str, Any]]:
    data = load_auth_store(path)
    profiles = data["profiles"]
    now_ms = int(time.time() * 1000)
    results: list[dict[str, Any]] = []
    for index, profile_id in enumerate(ordered_codex_profile_ids(data)):
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            continue
        expires = profile.get("expires")
        expires_ms = int(expires) if isinstance(expires, int | float) else None
        account_id = profile.get("accountId")
        if not isinstance(account_id, str) or not account_id.strip():
            account_id = None
        results.append(
            {
                "profile_id": profile_id,
                "provider": profile.get("provider"),
                "type": profile.get("type"),
                "account_id": account_id,
                "expires": expires_ms,
                "expires_at": format_expires_at(expires_ms),
                "expired": bool(expires_ms is not None and expires_ms <= now_ms),
                "order_index": index,
            }
        )
    return results


def upsert_codex_profile(
    path: Path,
    profile_id: str,
    creds: dict[str, Any],
    *,
    promote: bool = False,
) -> None:
    def _update(data: dict[str, Any]) -> None:
        profiles = data["profiles"]
        order = data["order"]
        profiles[profile_id] = {
            "type": "oauth",
            "provider": CODEX_PROVIDER,
            "access": creds["access"],
            "refresh": creds["refresh"],
            "expires": int(creds["expires"]),
            "accountId": creds.get("accountId"),
        }
        provider_order = _provider_order(data, CODEX_PROVIDER)
        provider_order = [value for value in provider_order if value != profile_id]
        if promote:
            provider_order.insert(0, profile_id)
        elif profile_id not in provider_order:
            provider_order.append(profile_id)
        order[CODEX_PROVIDER] = provider_order

    _mutate_json(path, default={"version": 1, "profiles": {}, "order": {}}, update=_update)


def resolve_profile_ids(
    path: Path,
    *,
    configured_profile_ids: Sequence[str] | None = None,
    primary_profile_id: str | None = None,
) -> list[str]:
    available = [profile["profile_id"] for profile in list_codex_profiles(path)]
    if configured_profile_ids:
        seen: set[str] = set()
        ordered: list[str] = []
        for profile_id in configured_profile_ids:
            normalized = profile_id.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if normalized in available:
                ordered.append(normalized)
        return ordered
    if primary_profile_id:
        normalized_primary = primary_profile_id.strip()
        if normalized_primary in available:
            return [normalized_primary] + [
                value for value in available if value != normalized_primary
            ]
    return available


def default_runtime_state() -> dict[str, Any]:
    return {
        "version": RUNTIME_STATE_VERSION,
        "updated_at": utc_now_iso(),
        "rotation_index": 0,
        "profiles": {},
        "fallback": {
            "enabled": False,
            "model": None,
            "last_used_at": None,
            "last_error": None,
            "last_error_at": None,
        },
    }


def default_profile_runtime_state() -> dict[str, Any]:
    return {
        "status": "ready",
        "disabled_until": None,
        "last_error": None,
        "last_error_at": None,
        "last_success_at": None,
        "success_count": 0,
        "failure_count": 0,
        "last_probe_status": None,
        "last_probe_message": None,
        "last_probe_at": None,
        "last_probe_http_status": None,
        "last_probe_latency_ms": None,
    }


def load_runtime_state(path: Path) -> dict[str, Any]:
    data = _load_json(path, default=default_runtime_state())
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        data["profiles"] = {}
    fallback = data.get("fallback")
    if not isinstance(fallback, dict):
        data["fallback"] = default_runtime_state()["fallback"]
    if not isinstance(data.get("rotation_index"), int):
        data["rotation_index"] = 0
    data["updated_at"] = str(data.get("updated_at") or utc_now_iso())
    return data


def load_runtime_state_or_default(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return default_runtime_state()
    try:
        return load_runtime_state(path)
    except (OSError, ValueError, TypeError, RuntimeError):
        return default_runtime_state()


def mutate_runtime_state(
    path: Path,
    update: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    def _apply(payload: dict[str, Any]) -> dict[str, Any]:
        current = payload if isinstance(payload, dict) else default_runtime_state()
        merged = update(current)
        result = merged if isinstance(merged, dict) else current
        result["version"] = RUNTIME_STATE_VERSION
        result["updated_at"] = utc_now_iso()
        return result

    payload = _mutate_json(
        path,
        default=default_runtime_state(),
        update=_apply,
        file_mode=RUNTIME_STATE_FILE_MODE,
        lock_mode=RUNTIME_STATE_LOCK_MODE,
        recover_read_errors=True,
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected runtime state dict while updating {path}")
    return payload


def prune_runtime_state(
    runtime_state: dict[str, Any], active_profile_ids: Iterable[str]
) -> dict[str, Any]:
    payload = json.loads(json.dumps(runtime_state))
    active = set(active_profile_ids)
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        payload["profiles"] = {}
        return payload
    payload["profiles"] = {
        profile_id: state
        for profile_id, state in profiles.items()
        if isinstance(profile_id, str) and profile_id in active and isinstance(state, dict)
    }
    return payload


def build_account_status_rows(
    auth_profiles_path: Path,
    runtime_state_path: Path | None,
    *,
    configured_profile_ids: Sequence[str] | None = None,
    primary_profile_id: str | None = None,
) -> list[dict[str, Any]]:
    profile_rows = list_codex_profiles(auth_profiles_path) if auth_profiles_path.exists() else []
    profile_order = (
        resolve_profile_ids(
            auth_profiles_path,
            configured_profile_ids=configured_profile_ids,
            primary_profile_id=primary_profile_id,
        )
        if auth_profiles_path.exists()
        else []
    )
    if not profile_order:
        profile_order = [row["profile_id"] for row in profile_rows]
    profile_by_id = {row["profile_id"]: row for row in profile_rows}
    ordered_rows = [
        profile_by_id[profile_id] for profile_id in profile_order if profile_id in profile_by_id
    ]
    for row in profile_rows:
        if row["profile_id"] not in profile_order:
            ordered_rows.append(row)
    runtime_state = load_runtime_state_or_default(runtime_state_path)
    runtime_profiles = runtime_state.get("profiles")
    if not isinstance(runtime_profiles, dict):
        runtime_profiles = {}
    now_ts = time.time()
    results: list[dict[str, Any]] = []
    for row in ordered_rows:
        state = runtime_profiles.get(row["profile_id"])
        if not isinstance(state, dict):
            state = {}
        disabled_until = state.get("disabled_until")
        disabled_until_ts = (
            float(disabled_until) if isinstance(disabled_until, int | float) else None
        )
        cooldown_active = bool(disabled_until_ts and disabled_until_ts > now_ts)
        results.append(
            {
                **row,
                "status": str(state.get("status") or ("expired" if row["expired"] else "ready")),
                "cooldown_active": cooldown_active,
                "disabled_until": disabled_until_ts,
                "disabled_until_at": (
                    datetime.fromtimestamp(disabled_until_ts, tz=UTC).isoformat()
                    if disabled_until_ts
                    else None
                ),
                "last_error": str(state.get("last_error") or "").strip() or None,
                "last_error_at": str(state.get("last_error_at") or "").strip() or None,
                "last_success_at": str(state.get("last_success_at") or "").strip() or None,
                "success_count": int(state.get("success_count") or 0),
                "failure_count": int(state.get("failure_count") or 0),
                "last_probe_status": str(state.get("last_probe_status") or "").strip() or None,
                "last_probe_message": str(state.get("last_probe_message") or "").strip() or None,
                "last_probe_at": str(state.get("last_probe_at") or "").strip() or None,
                "last_probe_http_status": (
                    int(state.get("last_probe_http_status"))
                    if isinstance(state.get("last_probe_http_status"), int)
                    else None
                ),
                "last_probe_latency_ms": (
                    int(state.get("last_probe_latency_ms"))
                    if isinstance(state.get("last_probe_latency_ms"), int)
                    else None
                ),
                "masked_account_id": mask_account_id(row["account_id"]),
            }
        )
    return results
