from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from core.orchestra_agents.agent_mux_runtime.backend_types import AgentMuxRunRequest
from core.orchestra_agents.agent_mux_runtime.cli_adapter import NativeCliAdapter
from core.orchestra_agents.agent_mux_runtime.codex_config import (
    RuntimeCodexConfigRequest,
    create_runtime_codex_request,
    write_runtime_codex_config,
)
from core.orchestra_agents.agent_mux_runtime.dispatch_engine import (
    AgentMuxDispatchSpec,
    build_agent_mux_command,
    parse_agent_mux_result,
)
from core.orchestra_agents.agent_mux_runtime.session_types import SessionId


@dataclass(frozen=True)
class _ProcessEnvContext:
    agent_slug: str
    context_id: str
    event_id: str
    event_kind: str
    dispatch_id: str
    active_context_path: str


async def run_agent_mux(
    request: AgentMuxRunRequest,
    session_id: SessionId | None = None,
) -> dict[str, Any]:
    settings = request.settings
    cli_adapter = cast(NativeCliAdapter | None, getattr(settings, "cli_adapter", None))

    if session_id is not None and cli_adapter is not None:
        if cli_adapter.session_exists(session_id):
            return cli_adapter.resume_session(session_id, request.event)
        return cli_adapter.start_session(session_id, request.event)

    codex_home = Path(settings.state_root).expanduser().resolve() / "home"
    write_runtime_codex_config(
        create_runtime_codex_request(
            RuntimeCodexConfigRequest(
                codex_home=codex_home,
                omniroute_url=settings.omniroute_url,
                route_policy=settings.llm_route_policy,
                model=settings.default_model,
                mcp_servers=settings.mcp_servers,
            ),
            agent_slug=request.agent_slug,
            active_context_path=request.active_context_path,
            pythonpath=str(os.getenv("PYTHONPATH") or f"/workspace/src:{request.working_dir}"),
            agent_working_dir=request.working_dir,
        )
    )
    spec = AgentMuxDispatchSpec(
        dispatch_id=request.dispatch_id,
        prompt=request.prompt,
        cwd=request.working_dir,
        artifact_dir=str(request.artifact_dir),
        system_prompt=request.system_prompt,
        role=settings.role,
        variant=settings.variant,
        engine=settings.engine,
        model=settings.default_model,
        timeout_sec=settings.agent_timeout_seconds,
        engine_opts={"close_stdin_after_start": True},
    )
    process = await asyncio.create_subprocess_exec(
        *build_agent_mux_command(settings.agent_mux_binary),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=request.working_dir,
        env=_process_env(
            settings=settings,
            codex_home=codex_home,
            context=_ProcessEnvContext(
                agent_slug=request.agent_slug,
                context_id=request.context_id,
                event_id=str(request.event.event_id or request.dispatch_id),
                event_kind=str(request.event.event_kind or "event"),
                dispatch_id=request.dispatch_id,
                active_context_path=request.active_context_path,
            ),
        ),
    )
    return {"process": process, "stdin_payload": _stdin_payload(spec)}


def _process_env(
    *,
    settings: Any,
    codex_home: Path,
    context: _ProcessEnvContext,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(codex_home),
            "CODEX_HOME": str(codex_home / ".codex"),
            "OMNIROUTE_API_KEY": settings.omniroute_api_key,
            "ORCHESTRA_AGENT_SLUG": context.agent_slug,
            "ORCHESTRA_CONTEXT_ID": context.context_id,
            "AGENT_MUX_CONTEXT_ID": context.context_id,
            "AGENT_MUX_EVENT_ID": context.event_id,
            "AGENT_MUX_EVENT_KIND": context.event_kind,
            "AGENT_MUX_DISPATCH_ID": context.dispatch_id,
            "AGENT_MUX_ACTIVE_CONTEXT_PATH": context.active_context_path,
            "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH": context.active_context_path,
        }
    )
    return env


async def collect_agent_mux_result(
    process: asyncio.subprocess.Process, stdin_payload: bytes
) -> dict[str, Any]:
    stdout_data, stderr_data = await process.communicate(stdin_payload)
    if process.returncode != 0:
        error_text = stderr_data.decode("utf-8", errors="replace").strip()
        if not error_text:
            error_text = stdout_data.decode("utf-8", errors="replace").strip()
        raise RuntimeError(error_text or f"agent-mux exited with code {process.returncode}")
    return parse_agent_mux_result(stdout_data.decode("utf-8", errors="replace"))


def _stdin_payload(spec: AgentMuxDispatchSpec) -> bytes:
    return json.dumps(spec.to_stdin_payload(), ensure_ascii=False).encode("utf-8")
