from __future__ import annotations

import asyncio
import importlib
import json
import os
import typing
from pathlib import Path

from core.orchestra_agents.backends.agent_mux.config import codex as codex_runtime
from core.orchestra_agents.backends.agent_mux.dispatch import engine as dispatch_engine
from core.orchestra_agents.backends.agent_mux.internal.session_types import SessionId
from core.orchestra_agents.backends.agent_mux.process.types import AgentMuxRunRequest


class _CliAdapter(typing.Protocol):
    def session_exists(self, session_id: SessionId) -> bool: ...

    def resume_session(
        self,
        session_id: SessionId,
        event: typing.Any,
    ) -> dict[str, typing.Any]: ...

    def start_session(
        self,
        session_id: SessionId,
        event: typing.Any,
    ) -> dict[str, typing.Any]: ...


async def run_agent_mux(
    request: AgentMuxRunRequest,
    session_id: SessionId | None = None,
) -> dict[str, typing.Any]:
    return await _AgentMuxRunner(request, session_id).run()


async def collect_agent_mux_result(
    process: asyncio.subprocess.Process,
    stdin_payload: bytes,
    *,
    close_stdin_after_start: bool,
) -> dict[str, typing.Any]:
    stdout_data, stderr_data = await process.communicate(stdin_payload)
    if process.returncode != 0:
        error_text = stderr_data.decode("utf-8", errors="replace").strip()
        if not error_text:
            error_text = stdout_data.decode("utf-8", errors="replace").strip()
        raise RuntimeError(error_text or f"agent-mux exited with code {process.returncode}")
    return dispatch_engine.parse_agent_mux_result(stdout_data.decode("utf-8", errors="replace"))


def _stdin_payload(spec: dispatch_engine.AgentMuxDispatchSpec) -> bytes:
    return json.dumps(spec.to_stdin_payload(), ensure_ascii=False).encode("utf-8")


class _AgentMuxRunner:
    def __init__(
        self,
        request: AgentMuxRunRequest,
        session_id: SessionId | None,
    ) -> None:
        self._request = request
        self._session_id = session_id

    async def run(self) -> dict[str, typing.Any]:
        settings = self._request.settings
        adapter = typing.cast(
            _CliAdapter | None,
            getattr(settings, "cli_adapter", None),
        )
        if self._session_id is not None and adapter is not None:
            if adapter.session_exists(self._session_id):
                return adapter.resume_session(self._session_id, self._request.event)
            return adapter.start_session(self._session_id, self._request.event)

        codex_home = Path(settings.state_root).expanduser().resolve() / "home"
        self._write_codex_config(codex_home)
        self._install_runtime_home(codex_home, model=settings.default_model)
        close_stdin_after_start = self._should_close_stdin_after_start(
            engine=settings.engine,
        )
        process = await asyncio.create_subprocess_exec(
            *dispatch_engine.build_agent_mux_command(settings.agent_mux_binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._request.working_dir,
            env=self._process_env(settings=settings, codex_home=codex_home),
        )
        return {
            "process": process,
            "stdin_payload": _stdin_payload(self._dispatch_spec(close_stdin_after_start)),
            "close_stdin_after_start": close_stdin_after_start,
        }

    def _write_codex_config(self, codex_home: Path) -> None:
        settings = self._request.settings
        codex_runtime.write_runtime_codex_config(
            codex_runtime.create_runtime_codex_request(
                codex_runtime.RuntimeCodexConfigRequest(
                    codex_home=codex_home,
                    omniroute_url=settings.omniroute_url,
                    route_policy=settings.llm_route_policy,
                    model=settings.default_model,
                    mcp_servers=settings.mcp_servers,
                ),
                agent_slug=self._request.agent_slug,
                active_context_path=self._request.active_context_path,
                pythonpath=str(
                    os.getenv("PYTHONPATH") or f"/workspace/src:{self._request.working_dir}"
                ),
                agent_working_dir=self._request.working_dir,
            )
        )

    def _dispatch_spec(
        self,
        close_stdin_after_start: bool,
    ) -> dispatch_engine.AgentMuxDispatchSpec:
        settings = self._request.settings
        return dispatch_engine.AgentMuxDispatchSpec(
            dispatch_id=self._request.dispatch_id,
            prompt=self._request.prompt,
            cwd=self._request.working_dir,
            artifact_dir=str(self._request.artifact_dir),
            system_prompt=self._request.system_prompt,
            role=settings.role or "worker",
            variant=settings.variant,
            engine=settings.engine,
            model=settings.default_model,
            timeout_sec=settings.agent_timeout_seconds,
            engine_opts={
                "close_stdin_after_start": close_stdin_after_start,
            },
        )

    def _process_env(
        self,
        *,
        settings: typing.Any,
        codex_home: Path,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(codex_home),
                "CODEX_HOME": str(codex_home / ".codex"),
                "OMNIROUTE_API_KEY": settings.omniroute_api_key,
                "ORCHESTRA_AGENT_SLUG": self._request.agent_slug,
                "ORCHESTRA_CONTEXT_ID": self._request.context_id,
                "AGENT_MUX_CONTEXT_ID": self._request.context_id,
                "AGENT_MUX_EVENT_ID": str(
                    self._request.event.event_id or self._request.dispatch_id
                ),
                "AGENT_MUX_EVENT_KIND": str(self._request.event.event_kind or "event"),
                "AGENT_MUX_DISPATCH_ID": self._request.dispatch_id,
                "AGENT_MUX_ACTIVE_CONTEXT_PATH": self._request.active_context_path,
                "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH": self._request.active_context_path,
            }
        )
        return env

    @staticmethod
    def _should_close_stdin_after_start(*, engine: str) -> bool:
        return str(engine).strip().lower() == "codex"

    @staticmethod
    def _install_runtime_home(codex_home: Path, *, model: str) -> None:
        runtime_home_module = importlib.import_module(
            "core.orchestra_agents.backends.agent_mux.process.runtime_home"
        )
        runtime_home_module.install_runtime_agent_mux_home(codex_home, model=model)
