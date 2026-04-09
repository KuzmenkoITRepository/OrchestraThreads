"""Validation and config helpers for backend switch operations."""

from __future__ import annotations

from typing import Any

from core.orchestra_agents.manifest import AgentManifest

SUPPORTED_SWITCH_BACKENDS = (
    "sgr_minimax",
    "agent_mux",
    "opencode_omo",
)
DEFAULT_SWITCH_PREPARE_MAX_MS = 1500.0
_CONTROLLED_ROLE = "worker"
_CONTROLLED_ROUTE_POLICY = "codex_only"
_CONTROLLED_LLM_ROUTE_POLICY = "minimax_only"
_CONTROLLED_MODEL = "cx/gpt-5.4-mini"


def validate_supported(backend_type: str) -> None:
    """Raise if backend_type is not in the supported subset."""
    if backend_type in SUPPORTED_SWITCH_BACKENDS:
        return
    supported = ", ".join(SUPPORTED_SWITCH_BACKENDS)
    raise ValueError(
        f"unsupported backend switch target {backend_type!r}; supported: {supported}",
    )


def validate_switch_source(manifest: AgentManifest) -> None:
    """Raise if manifest is outside the controlled switch subset."""
    if is_controlled_switch_ready(manifest):
        return
    raise ValueError(
        "source manifest is outside the supported switch subset; "
        "use a controlled temp manifest with route_policy and model",
    )


def is_controlled_switch_ready(
    manifest: AgentManifest,
) -> bool:
    """Check if a manifest supports the controlled switch subset."""
    if manifest.backend.type not in SUPPORTED_SWITCH_BACKENDS:
        return False
    keys = set(manifest.backend.config)
    return {"route_policy", "model"}.issubset(keys)


def controlled_config(
    existing: dict[str, Any],
) -> dict[str, Any]:
    """Build controlled config from existing or defaults."""
    return {
        "role": _pick(existing, "role", _CONTROLLED_ROLE),
        "route_policy": _pick(
            existing,
            "route_policy",
            _CONTROLLED_ROUTE_POLICY,
        ),
        "llm_route_policy": _pick_fallback(
            existing,
            "llm_route_policy",
            "route_policy",
            _CONTROLLED_LLM_ROUTE_POLICY,
        ),
        "model": _pick(existing, "model", _CONTROLLED_MODEL),
    }


def _pick(
    cfg: dict[str, Any],
    key: str,
    default: str,
) -> str:
    found = str(cfg.get(key) or "").strip()
    return found if found else default


def _pick_fallback(
    cfg: dict[str, Any],
    primary: str,
    fallback: str,
    default: str,
) -> str:
    for key in (primary, fallback):
        found = str(cfg.get(key) or "").strip()
        if found:
            return found
    return default
