from __future__ import annotations

import base64
import json
import os
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"
JWT_CLAIM_PATH = "https://api.openai.com/auth"


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def extract_account_id(access_token: str) -> str:
    payload = _decode_jwt_payload(access_token)
    auth = payload.get(JWT_CLAIM_PATH) if isinstance(payload, dict) else None
    if not isinstance(auth, dict):
        raise RuntimeError("Failed to extract accountId from token")
    account_id = auth.get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id:
        raise RuntimeError("Failed to extract accountId from token")
    return account_id


def resolve_default_auth_profiles_path() -> Path:
    explicit = os.getenv("CODEX_AUTH_PROFILES_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    codex_home = os.getenv("CODEX_HOME", "").strip()
    if codex_home:
        return Path(codex_home).expanduser() / "openclaw" / "auth-profiles.json"
    return Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def pick_openclaw_profile(
    auth_profiles_path: Path, profile_id: str | None
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    data = load_json(auth_profiles_path)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise RuntimeError(f'Missing "profiles" object in {auth_profiles_path}')
    chosen_profile_id = profile_id
    if chosen_profile_id:
        profile = profiles.get(chosen_profile_id)
        if not isinstance(profile, dict):
            raise RuntimeError(f"Profile {chosen_profile_id!r} not found in {auth_profiles_path}")
    else:
        ordered = data.get("order")
        provider_order = ordered.get("openai-codex") if isinstance(ordered, dict) else None
        if isinstance(provider_order, list):
            for candidate in provider_order:
                if isinstance(candidate, str) and isinstance(profiles.get(candidate), dict):
                    chosen_profile_id = candidate
                    break
        if not chosen_profile_id:
            for candidate_id, candidate in profiles.items():
                if isinstance(candidate, dict) and candidate.get("provider") == "openai-codex":
                    chosen_profile_id = candidate_id
                    break
        if not chosen_profile_id:
            raise RuntimeError(
                f"No openai-codex OAuth profile found in {auth_profiles_path}. Use a Codex login flow first."
            )
        profile = profiles[chosen_profile_id]
    if profile.get("type") != "oauth":
        raise RuntimeError(
            f"Profile {chosen_profile_id!r} exists but is not type=oauth: {profile.get('type')!r}"
        )
    if profile.get("provider") != "openai-codex":
        raise RuntimeError(
            f"Profile {chosen_profile_id!r} is for provider {profile.get('provider')!r}, not openai-codex"
        )
    access = profile.get("access")
    refresh = profile.get("refresh")
    expires = profile.get("expires")
    if not isinstance(access, str) or not access:
        raise RuntimeError(f"Profile {chosen_profile_id!r} is missing access token")
    if not isinstance(refresh, str) or not refresh:
        raise RuntimeError(f"Profile {chosen_profile_id!r} is missing refresh token")
    if not isinstance(expires, int | float):
        raise RuntimeError(f"Profile {chosen_profile_id!r} is missing expires timestamp")
    creds = {
        "access": access,
        "refresh": refresh,
        "expires": int(expires),
        "accountId": profile.get("accountId"),
    }
    if not isinstance(creds["accountId"], str) or not creds["accountId"]:
        raise RuntimeError(f"Profile {chosen_profile_id!r} is missing accountId")
    return chosen_profile_id, creds, data


def http_form_post(url: str, fields: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected token response from {url}: {parsed!r}")
    return parsed


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    result = http_form_post(
        TOKEN_URL,
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
            "redirect_uri": REDIRECT_URI,
        },
    )
    access = result.get("access_token")
    refresh = result.get("refresh_token") or refresh_token
    expires_in = result.get("expires_in")
    if not isinstance(access, str) or not access:
        raise RuntimeError("Token refresh response missing access_token")
    if not isinstance(refresh, str) or not refresh:
        raise RuntimeError("Token refresh response missing refresh_token")
    if not isinstance(expires_in, int | float):
        raise RuntimeError("Token refresh response missing expires_in")
    return {
        "access": access,
        "refresh": refresh,
        "expires": int(time.time() * 1000 + int(expires_in) * 1000),
        "accountId": extract_account_id(access),
    }


def ensure_fresh_credentials(creds: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if int(time.time() * 1000) < int(creds["expires"]):
        return creds, False
    refreshed = refresh_access_token(str(creds["refresh"]))
    return refreshed, True


def clamp_reasoning_effort(model_id: str, effort: str) -> str:
    short_id = model_id.split("/")[-1]
    if short_id.startswith(("gpt-5.2", "gpt-5.3", "gpt-5.4")) and effort == "minimal":
        return "low"
    if short_id == "gpt-5.1" and effort == "xhigh":
        return "high"
    if short_id == "gpt-5.1-codex-mini" and effort in {"high", "xhigh"}:
        return "high"
    if short_id == "gpt-5.1-codex-mini":
        return "medium"
    return effort


def resolve_codex_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/codex/responses"):
        return normalized
    if normalized.endswith("/codex"):
        return normalized + "/responses"
    return normalized + "/codex/responses"


def build_headers(access_token: str, account_id: str, session_id: str | None) -> dict[str, str]:
    system_name = platform.system().lower() or "unknown"
    release = platform.release() or "unknown"
    machine = platform.machine() or "unknown"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": "pi",
        "User-Agent": f"pi ({system_name} {release}; {machine})",
        "accept": "text/event-stream",
        "content-type": "application/json",
    }
    if session_id:
        headers["session_id"] = session_id
    return headers


def parse_error_payload(status_code: int, raw: str) -> str:
    message = raw or f"HTTP {status_code}"
    try:
        parsed = json.loads(raw)
    except Exception:
        return message
    if not isinstance(parsed, dict):
        return message
    detail = parsed.get("detail")
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(detail, dict):
        detail_message = detail.get("message")
        if isinstance(detail_message, str) and detail_message:
            return detail_message
    error = parsed.get("error")
    if not isinstance(error, dict):
        return message
    code = str(error.get("code") or error.get("type") or "")
    if status_code == 429 or any(
        marker in code.lower()
        for marker in ("usage_limit_reached", "usage_not_included", "rate_limit_exceeded")
    ):
        return error.get("message") or "You have hit your ChatGPT usage limit."
    return str(error.get("message") or message)
