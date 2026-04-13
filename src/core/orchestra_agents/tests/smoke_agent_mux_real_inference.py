# flake8: noqa: WPS201
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

_DEFAULT_PROXY_URL = "http://orchestra-wet:8100"
_DEFAULT_MODELS_URL = "http://orchestra-omniroute:20128/v1/models"
_DEFAULT_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class _SmokeCase:
    family: str
    model: str
    route_policy: str
    token: str


@dataclass(frozen=True)
class _EventStub:
    event_id: str
    event_kind: str


@dataclass(frozen=True)
class _SmokeResult:
    family: str
    model: str
    route_policy: str
    listed: bool
    ok: bool
    status: str
    reason: str | None
    preview: str | None


def _env_model(name: str, default: str) -> str:
    return str(os.getenv(name) or default).strip() or default


def _smoke_cases() -> tuple[_SmokeCase, ...]:
    return (
        _SmokeCase(
            family="cx",
            model=_env_model("OT_SMOKE_MODEL_CX", "cx/gpt-5.1-codex-mini"),
            route_policy="codex_only",
            token="CX_SMOKE_OK",
        ),
    )


def _json_get(url: str) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=15) as response:  # noqa: S310, WPS421
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def _listed_models() -> set[str]:
    models_url = str(os.getenv("OT_SMOKE_MODELS_URL") or _DEFAULT_MODELS_URL).strip()
    try:
        payload = _json_get(models_url)
    except (OSError, URLError, json.JSONDecodeError):
        return set()
    items = payload.get("data")
    if not isinstance(items, list):
        return set()
    return {
        str(item.get("id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _preview_text(result: dict[str, object]) -> str | None:
    for field_name in ("response", "handoff_summary", "reason"):
        value = str(result.get(field_name) or "").strip()
        if value:
            return value[:200]
    return None


def _build_settings(case: _SmokeCase, root_dir: Path) -> Any:
    from core.orchestra_agents.backends.agent_mux.backend_settings import (
        build_runtime_settings,  # noqa: WPS433
    )

    return build_runtime_settings(
        {
            "state_root": str(root_dir / case.family / "state"),
            "artifact_root": str(root_dir / case.family / "artifacts"),
            "llm_proxy_url": str(os.getenv("LLM_PROXY_URL") or _DEFAULT_PROXY_URL),
            "llm_proxy_api_key": str(os.getenv("LLM_PROXY_API_KEY") or "").strip(),
            "llm_route_policy": case.route_policy,
            "model": case.model,
            "timeout_seconds": _DEFAULT_TIMEOUT_SECONDS,
            "require_tool_call_for_response": False,
        },
        working_dir="/workspace",
        http_endpoint=None,
        llm_route_policy=case.route_policy,
        llm_model=case.model,
    )


def _request_prompt(case: _SmokeCase) -> str:
    return (
        "Return a plain-text reply without tools. "
        f"The reply must contain the exact token {case.token}. "
        "Keep it under twelve words."
    )


def _build_request(case: _SmokeCase, root_dir: Path) -> Any:
    from core.orchestra_agents.backends.agent_mux.backend_types import (
        AgentMuxRunRequest,  # noqa: WPS433
    )

    settings = _build_settings(case, root_dir)
    active_context_path = root_dir / case.family / "active_context.json"
    active_context_path.parent.mkdir(parents=True, exist_ok=True)
    return AgentMuxRunRequest(
        event=_EventStub(event_id=f"smoke-{case.family}", event_kind="smoke_test"),
        dispatch_id=f"dispatch-{case.family}",
        artifact_dir=Path(settings.artifact_root),
        working_dir="/workspace",
        agent_slug=f"smoke-{case.family}",
        context_id=f"ctx-{case.family}",
        system_prompt="Reply directly. No tools. No files. No commands.",
        settings=settings,
        prompt=_request_prompt(case),
        active_context_path=str(active_context_path),
    )


async def _collect_case_result(case: _SmokeCase, root_dir: Path) -> dict[str, object]:
    from core.orchestra_agents.backends.agent_mux.backend_process import (  # noqa: WPS433
        collect_agent_mux_result,
        run_agent_mux,
    )

    request = _build_request(case, root_dir)
    run_state = await run_agent_mux(request)
    return await collect_agent_mux_result(
        run_state["process"],
        run_state["stdin_payload"],
    )


def _failed_result(
    case: _SmokeCase,
    *,
    listed_models: set[str],
    reason: str,
) -> _SmokeResult:
    return _SmokeResult(
        family=case.family,
        model=case.model,
        route_policy=case.route_policy,
        listed=case.model in listed_models,
        ok=False,
        status="failed",
        reason=reason,
        preview=None,
    )


async def _run_case(case: _SmokeCase, listed_models: set[str], root_dir: Path) -> _SmokeResult:
    try:
        result = await _collect_case_result(case, root_dir)
    except Exception as exc:
        return _failed_result(case, listed_models=listed_models, reason=str(exc))
    status = str(result.get("status") or "").strip() or "unknown"
    return _SmokeResult(
        family=case.family,
        model=case.model,
        route_policy=case.route_policy,
        listed=case.model in listed_models,
        ok=status == "completed",
        status=status,
        reason=str(result.get("reason") or "").strip() or None,
        preview=_preview_text(result),
    )


def _emit_case(result: _SmokeResult) -> None:
    payload = json.dumps(
        {
            "family": result.family,
            "model": result.model,
            "route_policy": result.route_policy,
            "listed": result.listed,
            "ok": result.ok,
            "status": result.status,
            "reason": result.reason,
            "preview": result.preview,
        },
        ensure_ascii=False,
    )
    sys.stdout.write(f"{payload}\n")


async def _run_all_cases(root_dir: Path, listed_models: set[str]) -> list[_SmokeResult]:
    coroutines = [_run_case(case, listed_models, root_dir) for case in _smoke_cases()]
    results = await asyncio.gather(*coroutines)
    for item in results:
        _emit_case(item)
    return results


def _emit_summary(results: list[_SmokeResult]) -> int:
    summary = {
        "ok": all(item.ok for item in results),
        "results": [asdict(item) for item in results],
    }
    sys.stdout.write(f"{json.dumps(summary, ensure_ascii=False)}\n")
    return 0 if summary["ok"] else 1


async def _main() -> int:
    listed_models = _listed_models()
    with tempfile.TemporaryDirectory(prefix="mux_smoke_") as temp_dir:
        results = await _run_all_cases(Path(temp_dir), listed_models)
    return _emit_summary(results)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
