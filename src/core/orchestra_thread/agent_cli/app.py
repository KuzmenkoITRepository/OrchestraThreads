"""Manual CLI agent for exercising OrchestraThreads without an LLM runtime."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from core.orchestra_thread.agent_cli.callbacks import CallbackHandlers, CallbackLifecycle
from core.orchestra_thread.agent_cli.commands import CommandRouter
from core.orchestra_thread.agent_cli.output import OutputFormatter, OutputWriter
from core.orchestra_thread.client import OrchestraThreadsClient


class ManualAgentCLI:  # noqa: WPS214, WPS230 - REPL agent keeps stateful CLI/session surface in one runtime object.
    """A callback-capable manual agent with a small REPL."""

    def __init__(self, args: Any) -> None:
        self.agent_slug = str(args.slug)
        self.service_url = str(args.service_url).rstrip("/")
        self.listen_host = str(args.listen_host)
        self.listen_port = int(args.listen_port)
        self.advertise_host = str(args.advertise_host or args.listen_host)
        self.scheme = str(args.scheme)
        self.heartbeat_interval_seconds = max(2.0, float(args.heartbeat_interval))
        self.current_thread_id: str | None = None
        self.default_target_agent_slug = str(args.target or "").strip() or None
        self.thread_peers: dict[str, str] = {}
        self.inbox: deque[dict[str, Any]] = deque(maxlen=200)
        self.stop_signals: deque[dict[str, Any]] = deque(maxlen=50)
        self.http_runner: Any | None = None
        self.thread_client: OrchestraThreadsClient | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None
        self.shutdown_event = asyncio.Event()
        self._callback_handlers = CallbackHandlers(self)
        self._callback_lifecycle = CallbackLifecycle(self)
        self._command_router = CommandRouter(self)

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.advertise_host}:{self.listen_port}"

    async def start(self) -> None:
        self.thread_client = self.thread_client or OrchestraThreadsClient(
            base_url=self.service_url,
            timeout_seconds=10,
        )
        await self._callback_lifecycle.start_server()
        await self._callback_lifecycle.register()
        self.heartbeat_task = asyncio.create_task(
            self._callback_lifecycle.heartbeat_loop(),
            name=f"{self.agent_slug}-heartbeat",
        )

    async def stop(self) -> None:
        self.shutdown_event.set()
        if self.heartbeat_task is not None:
            self.heartbeat_task.cancel()
            await asyncio.gather(self.heartbeat_task, return_exceptions=True)
            self.heartbeat_task = None
        if self.http_runner is not None:
            await self.http_runner.cleanup()
            self.http_runner = None
        if self.thread_client is not None:
            await self.thread_client.close()
            self.thread_client = None

    async def _handle_health(self, request: Any) -> Any:
        return await self._callback_handlers.handle_health(request)

    async def _handle_event(self, request: Any) -> Any:
        return await self._callback_handlers.handle_event(request)

    async def _handle_stop(self, request: Any) -> Any:
        return await self._callback_handlers.handle_stop(request)

    async def _dispatch_command(self, raw: str) -> bool:
        return await self._command_router.dispatch(raw)


def _build_arg_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Manual CLI agent for OrchestraThreads")
    parser.add_argument("--slug", required=True, help="Agent slug used in threads")
    parser.add_argument(
        "--service-url", default="http://127.0.0.1:8788", help="Base URL of OrchestraThreads"
    )
    parser.add_argument(
        "--listen-host", default="127.0.0.1", help="Host for the local callback server"
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=0,
        help="Port for the local callback server. Use 0 to auto-pick a free port.",
    )
    parser.add_argument(
        "--advertise-host",
        default=None,
        help="Host advertised back to OrchestraThreads. Use host.docker.internal or a LAN IP when the service runs in Docker.",
    )
    parser.add_argument("--scheme", default="http", help="Scheme for advertised callback URLs")
    parser.add_argument(
        "--heartbeat-interval", type=float, default=10.0, help="Heartbeat interval in seconds"
    )
    parser.add_argument(
        "--target", help="Optional default chat target for human-friendly bare-message mode."
    )
    return parser


async def _main_async(args: Any) -> None:
    agent = ManualAgentCLI(args)
    await agent.start()
    try:
        await _run_repl(agent)
    except Exception:
        await agent.stop()
        raise
    await agent.stop()


async def _run_repl(agent: ManualAgentCLI) -> None:
    OutputWriter.print_help()
    while not agent.shutdown_event.is_set():
        raw = (await _read_repl_input(agent)).strip()
        if not raw:
            continue
        if await _dispatch_command_safe(agent, raw):
            return


async def _read_repl_input(agent: ManualAgentCLI) -> str:
    prompt = OutputFormatter.format_prompt(
        agent_slug=agent.agent_slug,
        current_thread_id=agent.current_thread_id,
        default_target_agent_slug=agent.default_target_agent_slug,
        thread_peers=agent.thread_peers,
    )
    try:
        return await asyncio.to_thread(input, f"{prompt}> ")
    except EOFError:
        return "quit"


async def _dispatch_command_safe(agent: ManualAgentCLI, raw: str) -> bool:
    try:
        return await agent._dispatch_command(raw)
    except Exception as exc:
        OutputWriter.write_line(f"[error] {exc}")
        return False


def main() -> None:
    args = _build_arg_parser().parse_args()
    asyncio.run(_main_async(args))
