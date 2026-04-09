from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.opencode.config_provider import (
    build_provider_entry,
)

_SCHEMA_URL = "https://opencode.ai/config.json"
_DEFAULT_MODEL = "gpt-5.4-mini"


def resolve_model(cfg: dict[str, Any]) -> str:
    return str(cfg.get("model") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def build_root_payload(model: str, cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": _SCHEMA_URL,
        "model": f"omniroute/{model}",
        "provider": {"omniroute": build_provider_entry(model, cfg)},
    }
