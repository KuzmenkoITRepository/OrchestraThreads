from __future__ import annotations

_CODEX_PREFIXES = frozenset(("cx", "codex"))
_MINIMAX_PREFIXES = frozenset(("minimax",))


def model_prefix(model: str | None) -> str | None:
    if model is None:
        return None
    text = model.strip()
    if not text or "/" not in text:
        return None
    prefix, _, _ = text.partition("/")
    normalized = prefix.strip().lower()
    return normalized or None


def infer_route_policy(model: str | None, fallback: str) -> str:
    prefix = model_prefix(model)
    if prefix in _CODEX_PREFIXES:
        return "codex_only"
    if prefix in _MINIMAX_PREFIXES:
        return "minimax_only"
    return fallback


def requires_streaming_chat(model: str | None) -> bool:
    return model_prefix(model) in _CODEX_PREFIXES
