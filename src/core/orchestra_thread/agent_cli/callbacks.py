"""Callback-server lifecycle and request handlers for the manual CLI."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from typing import Any

from core.orchestra_thread.agent_cli import output as cli_output
from core.orchestra_thread.agent_cli import state as cli_state

web = importlib.import_module("aiohttp.web")


class CallbackLifecycle:
    """Startup and heartbeat lifecycle for the callback server."""

    def __init__(self, cli: Any) -> None:
        self._cli = cli

    async def start_server(self) -> None:
        """Start the local callback server for event delivery."""
        app = web.Application()
        app.router.add_post("/event", self._cli._handle_event)
        app.router.add_post("/stop", self._cli._handle_stop)
        app.router.add_get("/healthz", self._cli._handle_health)
        runner = web.AppRunner(app)
        self._cli.http_runner = runner
        await runner.setup()
        site = web.TCPSite(runner, host=self._cli.listen_host, port=self._cli.listen_port)
        await site.start()
        self._refresh_bound_port(site)

    async def register(self) -> dict[str, Any]:
        """Register the manual agent with OrchestraThreads."""
        result = await cli_state.require_client(self._cli.thread_client).register_agent(
            agent_slug=self._cli.agent_slug,
            display_name=self._cli.agent_slug,
            base_url=self._cli.base_url,
            metadata={
                "kind": "manual-cli-agent",
                "argv": sys.argv,
            },
        )
        cli_output.OutputWriter.write_line(
            f"[register] {self._cli.agent_slug} -> {self._cli.base_url} "
            f"(lease={result.get('agent_lease_seconds')}s)"
        )
        return result

    async def heartbeat(self) -> None:
        """Send a single agent heartbeat."""
        try:
            await cli_state.require_client(self._cli.thread_client).heartbeat(
                agent_slug=self._cli.agent_slug,
            )
        except Exception as exc:
            cli_output.OutputWriter.write_line(f"[heartbeat-error] {exc}")

    async def heartbeat_loop(self) -> None:
        """Run background heartbeats until shutdown."""
        while not self._cli.shutdown_event.is_set():
            await asyncio.sleep(self._cli.heartbeat_interval_seconds)
            if self._cli.shutdown_event.is_set():
                return
            await self.heartbeat()

    def _refresh_bound_port(self, site: Any) -> None:
        sockets = getattr(site, "_server", None)
        if sockets is None or not getattr(sockets, "sockets", None):
            return
        self._cli.listen_port = int(sockets.sockets[0].getsockname()[1])


class CallbackHandlers:
    """HTTP callback handlers for CLI delivery endpoints."""

    def __init__(self, cli: Any) -> None:
        self._cli = cli

    async def handle_health(self, _: Any) -> Any:
        """Respond to health checks."""
        return web.json_response(
            {
                "status": "ok",
                "agent_slug": self._cli.agent_slug,
                "current_thread_id": self._cli.current_thread_id,
            }
        )

    async def handle_event(self, request: Any) -> Any:
        """Handle incoming event callbacks."""
        payload = await request.json()
        events = cli_state.payload_items(payload, key="events")
        for event in events:
            self._cli.inbox.append(event)
            self._update_peer_state(event)
            cli_output.OutputFormatter.print_event(event)
        return web.json_response({"accepted": True, "event_count": len(events)})

    async def handle_stop(self, request: Any) -> Any:
        """Handle stop callbacks from the thread service."""
        payload = await request.json()
        self._cli.stop_signals.append(payload)
        thread_id = str(payload.get("thread_id") or "").strip()
        cli_output.OutputWriter.write_line(f"\n[stop] {json.dumps(payload, ensure_ascii=False)}")
        if thread_id and thread_id == self._cli.current_thread_id:
            self._cli.current_thread_id = None
        return web.json_response({"accepted": True})

    def _update_peer_state(self, event: dict[str, Any]) -> None:
        thread_id = str(event.get("thread_id") or "").strip()
        peer_agent_slug = cli_state.peer_from_event(
            event,
            agent_slug=self._cli.agent_slug,
            thread_peers=self._cli.thread_peers,
        )
        if not thread_id or not peer_agent_slug:
            return
        self._cli.thread_peers[thread_id] = peer_agent_slug
        self._cli.current_thread_id = thread_id
        self._cli.default_target_agent_slug = peer_agent_slug
