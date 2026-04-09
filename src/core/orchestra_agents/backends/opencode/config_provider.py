from __future__ import annotations

import os
from typing import Any

_DEFAULT_OMNIROUTE_URL = "http://orchestra-omniroute:20128"
_CONTEXT_LIMIT = 1_000_000
_OUTPUT_LIMIT = 32_768
ProviderModel = dict[str, Any]
ProviderModelMap = dict[str, ProviderModel]


def build_provider_entry(model: str, cfg: dict[str, Any]) -> ProviderModel:
    return {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Omniroute",
        "options": _provider_options(cfg),
        "models": _provider_models(model, cfg),
    }


def _provider_options(cfg: dict[str, Any]) -> dict[str, str]:
    omniroute_url = str(
        cfg.get("omniroute_url") or os.getenv("OMNIROUTE_URL") or _DEFAULT_OMNIROUTE_URL
    )
    api_key = cfg.get("omniroute_api_key") or os.getenv("OMNIROUTE_API_KEY") or ""
    return {
        "baseURL": f"{omniroute_url.rstrip('/')}/v1",
        "apiKey": str(api_key).strip(),
    }


def _provider_models(model: str, cfg: dict[str, Any]) -> ProviderModelMap:
    names = [model]
    _extend_names(cfg.get("models"), names)
    return _model_map(names)


def _extend_names(raw_models: object, names: list[str]) -> None:
    if not isinstance(raw_models, list):
        return
    for raw_model in raw_models:
        normalized = _model_name(raw_model)
        if normalized and normalized not in names:
            names.append(normalized)


def _model_name(raw_model: Any) -> str:
    if isinstance(raw_model, str):
        return raw_model.strip()
    if isinstance(raw_model, dict):
        raw_name = raw_model.get("id") or raw_model.get("name") or ""
        return str(raw_name).strip()
    return ""


def _model_entry(name: str) -> ProviderModel:
    return {
        "name": name,
        "attachment": True,
        "limit": {
            "context": _CONTEXT_LIMIT,
            "output": _OUTPUT_LIMIT,
        },
    }


def _model_map(names: list[str]) -> ProviderModelMap:
    models: ProviderModelMap = {}
    for name in names:
        models[name] = _model_entry(name)
    return models
