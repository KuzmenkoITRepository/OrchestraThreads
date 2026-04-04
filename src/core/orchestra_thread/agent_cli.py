"""Manual CLI agent for exercising OrchestraThreads without an LLM runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shlex
import sys
from collections import deque
from typing import Any, Optional

from aiohttp import web

from .common import normalize_text_input
from .client import OrchestraThreadsClient


logger = logging.getLogger(__name__)


class ManualAgentCLI:
    """A callback-capable manual agent with a small REPL."""

    def __init__(
        self,
        *,
        agent_slug: str,
        service_url: str,
        listen_host: str,
        listen_port: int,
        advertise_host: str,
        scheme: str,
        heartbeat_interval_seconds: float,
        default_target_agent_slug: Optional[str] = None,
    ) -> None:
        self.agent_slug = agent_slug
        self.service_url = service_url.rstrip("/")
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.advertise_host = advertise_host
        self.scheme = scheme
        self.heartbeat_interval_seconds = max(2.0, heartbeat_interval_seconds)
        self.current_thread_id: Optional[str] = None
        self.default_target_agent_slug = str(default_target_agent_slug or "").strip() or None
        self.thread_peers: dict[str, str] = {}
        self.inbox: deque[dict[str, Any]] = deque(maxlen=200)
        self.stop_signals: deque[dict[str, Any]] = deque(maxlen=50)
        self.http_runner: Optional[web.AppRunner] = None
        self.thread_client: Optional[OrchestraThreadsClient] = None
        self.heartbeat_task: Optional[asyncio.Task[None]] = None
        self.shutdown_event = asyncio.Event()

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.advertise_host}:{self.listen_port}"

    async def start(self) -> None:
        if self.thread_client is None:
            self.thread_client = OrchestraThreadsClient(base_url=self.service_url, timeout_seconds=10)
        await self._start_callback_server()
        await self.register()
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name=f"{self.agent_slug}-heartbeat")

    async def stop(self) -> None:
        self.shutdown_event.set()
        if self.heartbeat_task is not None:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
        if self.http_runner is not None:
            await self.http_runner.cleanup()
            self.http_runner = None
        if self.thread_client is not None:
            await self.thread_client.close()
            self.thread_client = None

    async def _start_callback_server(self) -> None:
        app = web.Application()
        app.router.add_post("/event", self._handle_event)
        app.router.add_post("/stop", self._handle_stop)
        app.router.add_get("/healthz", self._handle_health)
        self.http_runner = web.AppRunner(app)
        await self.http_runner.setup()
        site = web.TCPSite(self.http_runner, host=self.listen_host, port=self.listen_port)
        await site.start()
        sockets = getattr(site, "_server", None)
        if sockets is not None and getattr(sockets, "sockets", None):
            bound_port = sockets.sockets[0].getsockname()[1]
            self.listen_port = int(bound_port)

    async def register(self) -> dict[str, Any]:
        if self.thread_client is None:
            raise RuntimeError("HTTP client is not started")
        result = await self.thread_client.register_agent(
            agent_slug=self.agent_slug,
            display_name=self.agent_slug,
            base_url=self.base_url,
            metadata={
                "kind": "manual-cli-agent",
                "argv": sys.argv,
            },
        )
        print(
            f"[register] {self.agent_slug} -> {self.base_url} "
            f"(lease={result.get('agent_lease_seconds')}s)"
        )
        return result

    async def heartbeat(self) -> None:
        try:
            if self.thread_client is None:
                raise RuntimeError("HTTP client is not started")
            await self.thread_client.heartbeat(agent_slug=self.agent_slug)
        except Exception as exc:
            print(f"[heartbeat-error] {exc}")

    async def _heartbeat_loop(self) -> None:
        while not self.shutdown_event.is_set():
            await asyncio.sleep(self.heartbeat_interval_seconds)
            if self.shutdown_event.is_set():
                return
            await self.heartbeat()

    async def _handle_health(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "agent_slug": self.agent_slug,
                "current_thread_id": self.current_thread_id,
            }
        )

    async def _handle_event(self, request: web.Request) -> web.Response:
        payload = await request.json()
        events = payload.get("events") if isinstance(payload.get("events"), list) else []
        for event in events:
            self.inbox.append(event)
            thread_id = str(event.get("thread_id") or "").strip()
            peer_agent_slug = self._peer_from_event(event)
            if thread_id and peer_agent_slug:
                self.thread_peers[thread_id] = peer_agent_slug
                self.current_thread_id = thread_id
                self.default_target_agent_slug = peer_agent_slug
            self._print_event(event)
        return web.json_response({"accepted": True, "event_count": len(events)})

    async def _handle_stop(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.stop_signals.append(payload)
        thread_id = str(payload.get("thread_id") or "").strip()
        print(f"\n[stop] {json.dumps(payload, ensure_ascii=False)}")
        if thread_id and thread_id == self.current_thread_id:
            self.current_thread_id = None
        return web.json_response({"accepted": True})

    def _print_event(self, event: dict[str, Any]) -> None:
        preview = " ".join(str(event.get("message_text") or "").split())
        if len(preview) > 160:
            preview = f"{preview[:157]}..."
        print(
            "\n[event] "
            f"thread={event.get('thread_id')} "
            f"seq={event.get('sequence_no')} "
            f"kind={event.get('event_kind')} "
            f"status={event.get('notification_status') or '-'} "
            f"from={event.get('from_agent_slug')} "
            f"text={preview}"
        )

    async def run_repl(self) -> None:
        self._print_help()
        while not self.shutdown_event.is_set():
            try:
                raw = await asyncio.to_thread(input, f"{self._prompt()}> ")
            except EOFError:
                raw = "quit"
            raw = raw.strip()
            if not raw:
                continue
            try:
                should_stop = await self._dispatch_command(raw)
            except Exception as exc:
                print(f"[error] {exc}")
                continue
            if should_stop:
                return

    def _prompt(self) -> str:
        current_peer = self.thread_peers.get(self.current_thread_id or "", None)
        if self.current_thread_id and current_peer:
            return f"[{self.agent_slug} -> {current_peer} #{self.current_thread_id[:8]}]"
        if self.default_target_agent_slug:
            return f"[{self.agent_slug} -> {self.default_target_agent_slug}]"
        return f"[{self.agent_slug}]"

    def _known_peer_for_current_thread(self) -> Optional[str]:
        if not self.current_thread_id:
            return None
        return self.thread_peers.get(self.current_thread_id)

    def _peer_from_event(self, event: dict[str, Any]) -> Optional[str]:
        thread_id = str(event.get("thread_id") or "").strip()
        from_agent_slug = str(event.get("from_agent_slug") or "").strip()
        to_agent_slug = str(event.get("to_agent_slug") or "").strip()
        if from_agent_slug and from_agent_slug != self.agent_slug and from_agent_slug != "orchestra_threads":
            return from_agent_slug
        if to_agent_slug and to_agent_slug != self.agent_slug and to_agent_slug != "orchestra_threads":
            return to_agent_slug
        if thread_id:
            return self.thread_peers.get(thread_id)
        return None

    async def _send_root_message(self, *, target: str, message: str) -> None:
        if self.thread_client is None:
            raise RuntimeError("HTTP client is not started")
        payload = await self.thread_client.send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            message_text=message,
        )
        thread_id = str(payload.get("thread", {}).get("thread_id") or "").strip()
        if thread_id:
            self.current_thread_id = thread_id
            self.thread_peers[thread_id] = target
        self.default_target_agent_slug = target
        self._print_message_ack(payload, target=target)

    async def _reply_current_thread(self, *, message: str) -> None:
        if self.thread_client is None:
            raise RuntimeError("HTTP client is not started")
        if not self.current_thread_id:
            raise RuntimeError("No current thread selected")
        target = self._known_peer_for_current_thread()
        if not target:
            raise RuntimeError(f"No known peer for thread {self.current_thread_id}")
        payload = await self.thread_client.send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            thread_id=self.current_thread_id,
            message_text=message,
        )
        self.default_target_agent_slug = target
        self._print_message_ack(payload, target=target)

    async def _send_child_message(self, *, target: str, message: str) -> None:
        if self.thread_client is None:
            raise RuntimeError("HTTP client is not started")
        if not self.current_thread_id:
            raise RuntimeError("No current parent thread selected")
        payload = await self.thread_client.send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            parent_thread_id=self.current_thread_id,
            message_text=message,
        )
        child_thread_id = str(payload.get("thread", {}).get("thread_id") or "").strip()
        if child_thread_id:
            self.current_thread_id = child_thread_id
            self.thread_peers[child_thread_id] = target
        self.default_target_agent_slug = target
        self._print_message_ack(payload, target=target)

    async def _send_notification(self, *, status: str, message: str) -> None:
        if self.thread_client is None:
            raise RuntimeError("HTTP client is not started")
        if not self.current_thread_id:
            raise RuntimeError("No current thread selected")
        target = self._known_peer_for_current_thread()
        if not target:
            raise RuntimeError(f"No known peer for thread {self.current_thread_id}")
        payload = await self.thread_client.send_notification(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            thread_id=self.current_thread_id,
            status=status,
            message_text=message,
        )
        self._print_notification_ack(payload, target=target)

    def _print_message_ack(self, payload: dict[str, Any], *, target: str) -> None:
        thread = payload.get("thread") or {}
        thread_id = str(thread.get("thread_id") or "").strip() or "-"
        status = str(thread.get("status") or "").strip() or "-"
        created = bool(payload.get("created_thread"))
        scope = str(thread.get("scope") or "").strip() or "root"
        created_text = "new" if created else "reused"
        print(f"[sent] to={target} thread={thread_id} scope={scope} status={status} route={created_text}")

    def _print_notification_ack(self, payload: dict[str, Any], *, target: str) -> None:
        thread = payload.get("thread") or {}
        event = payload.get("event") or {}
        print(
            f"[status] to={target} thread={thread.get('thread_id')} "
            f"thread_status={thread.get('status')} published={event.get('notification_status')}"
        )

    def _print_threads(self, payload: dict[str, Any]) -> None:
        threads = payload.get("threads") if isinstance(payload.get("threads"), list) else []
        if not threads:
            print("[threads] none")
            return
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            thread_id = str(thread.get("thread_id") or "").strip()
            participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
            participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
            peer = participant_b if participant_a == self.agent_slug else participant_a
            marker = "*" if thread_id and thread_id == self.current_thread_id else " "
            print(
                f"{marker} {thread_id} peer={peer or '?'} "
                f"status={thread.get('status')} scope={thread.get('scope')} owner={thread.get('owner_agent_slug')}"
            )

    def _print_agents(self, payload: dict[str, Any]) -> None:
        agents = payload.get("agents") if isinstance(payload.get("agents"), list) else []
        if not agents:
            print("[agents] none")
            return
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            print(
                f"{agent.get('agent_slug')} online={agent.get('online')} "
                f"last_seen_at={agent.get('last_seen_at')} base_url={agent.get('event_callback_url')}"
            )

    async def _handle_text_input(self, raw: str) -> bool:
        message = raw.strip()
        if not message:
            return False
        if message.startswith("@"):
            prefix, _, body = message.partition(" ")
            target = prefix[1:].strip()
            if not target or not body.strip():
                raise RuntimeError("Usage: @<target_agent_slug> <message>")
            await self._send_root_message(target=target, message=body.strip())
            return True
        if self.current_thread_id and self._known_peer_for_current_thread():
            await self._reply_current_thread(message=message)
            return True
        if self.default_target_agent_slug:
            await self._send_root_message(target=self.default_target_agent_slug, message=message)
            return True
        raise RuntimeError("No chat target selected. Use `chat <agent_slug>` or `@agent message`.")

    async def _dispatch_command(self, raw: str) -> bool:
        raw = normalize_text_input(raw).strip()
        if not raw:
            return False
        normalized_raw = raw[1:] if raw.startswith("/") else raw
        parts = shlex.split(normalized_raw)
        if not parts:
            return False
        command = parts[0].lower()
        if command in {"quit", "exit"}:
            return True
        if command == "help":
            self._print_help()
            return False
        if command == "register":
            await self.register()
            return False
        if command == "agents":
            if self.thread_client is None:
                raise RuntimeError("HTTP client is not started")
            payload = await self.thread_client.list_agents()
            self._print_agents(payload)
            return False
        if command == "threads":
            scope = "active"
            if len(parts) > 1:
                scope = parts[1]
            if self.thread_client is None:
                raise RuntimeError("HTTP client is not started")
            payload = await self.thread_client.list_threads(scope=scope)
            self._print_threads(payload)
            return False
        if command == "thread":
            thread_id = self.current_thread_id
            if len(parts) > 1:
                thread_id = parts[1]
            if not thread_id:
                raise RuntimeError("No current thread. Use `thread <thread_id>` or `use <thread_id>`.")
            if self.thread_client is None:
                raise RuntimeError("HTTP client is not started")
            payload = await self.thread_client.get_thread(thread_id=thread_id)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return False
        if command == "use":
            if len(parts) != 2:
                raise RuntimeError("Usage: use <thread_id>")
            self.current_thread_id = parts[1]
            peer = self.thread_peers.get(self.current_thread_id, '?')
            if peer and peer != '?':
                self.default_target_agent_slug = peer
            print(f"[current] thread={self.current_thread_id} peer={peer}")
            return False
        if command in {"chat", "dm"}:
            if len(parts) != 2:
                raise RuntimeError("Usage: chat <target_agent_slug>")
            target = parts[1].strip()
            self.default_target_agent_slug = target
            current_peer = self._known_peer_for_current_thread()
            if current_peer and current_peer != target:
                self.current_thread_id = None
            print(f"[chat] target={target} thread={self.current_thread_id or 'new-root-on-first-message'}")
            return False
        if command in {"leave", "clear"}:
            self.current_thread_id = None
            self.default_target_agent_slug = None
            print("[chat] cleared current thread and target")
            return False
        if command == "current":
            print(f"agent_slug={self.agent_slug}")
            print(f"current_thread_id={self.current_thread_id}")
            print(f"current_peer={self.thread_peers.get(self.current_thread_id or '', None)}")
            print(f"default_target_agent_slug={self.default_target_agent_slug}")
            return False
        if command == "inbox":
            limit = len(self.inbox)
            if len(parts) > 1:
                limit = max(1, int(parts[1]))
            items = list(self.inbox)[-limit:]
            print(json.dumps(items, ensure_ascii=False, indent=2))
            return False
        if command == "send":
            if len(parts) < 3:
                raise RuntimeError('Usage: send <target_agent_slug> "<message>"')
            await self._send_root_message(target=parts[1], message=" ".join(parts[2:]))
            return False
        if command == "reply":
            if len(parts) < 2:
                raise RuntimeError('Usage: reply "<message>"')
            await self._reply_current_thread(message=" ".join(parts[1:]))
            return False
        if command == "child":
            if len(parts) < 3:
                raise RuntimeError('Usage: child <target_agent_slug> "<message>"')
            await self._send_child_message(target=parts[1], message=" ".join(parts[2:]))
            return False
        if command == "notify":
            if len(parts) < 3:
                raise RuntimeError('Usage: notify <in_progress|review|done|closed> "<message>"')
            await self._send_notification(status=parts[1], message=" ".join(parts[2:]))
            return False
        if command == "say":
            if len(parts) < 2:
                raise RuntimeError('Usage: say "<message>"')
            await self._handle_text_input(" ".join(parts[1:]))
            return False
        handled = await self._handle_text_input(raw)
        if handled:
            return False
        raise RuntimeError(f"Unknown command: {command}")

    @staticmethod
    def _print_help() -> None:
        print(
            """
Commands:
  help
  register
  agents
  threads [active|all]
  thread [thread_id]
  chat <target_agent_slug>
  leave
  use <thread_id>
  current
  inbox [limit]
  @<target_agent_slug> <message>
  say "<message>"
  send <target_agent_slug> "<message>"
  reply "<message>"
  child <target_agent_slug> "<message>"
  notify <in_progress|review|done|closed> "<message>"
  /<command>        # optional slash-prefix for commands
  <message>         # send to current thread or selected chat target
  quit
            """.strip()
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual CLI agent for OrchestraThreads")
    parser.add_argument("--slug", required=True, help="Agent slug used in threads")
    parser.add_argument("--service-url", default="http://127.0.0.1:8788", help="Base URL of OrchestraThreads")
    parser.add_argument("--listen-host", default="127.0.0.1", help="Host for the local callback server")
    parser.add_argument("--listen-port", type=int, default=0, help="Port for the local callback server. Use 0 to auto-pick a free port.")
    parser.add_argument(
        "--advertise-host",
        default=None,
        help="Host advertised back to OrchestraThreads. Use host.docker.internal or a LAN IP when the service runs in Docker.",
    )
    parser.add_argument("--scheme", default="http", help="Scheme for advertised callback URLs")
    parser.add_argument("--heartbeat-interval", type=float, default=10.0, help="Heartbeat interval in seconds")
    parser.add_argument("--target", help="Optional default chat target for human-friendly bare-message mode.")
    return parser


async def _main_async(args: argparse.Namespace) -> None:
    agent = ManualAgentCLI(
        agent_slug=args.slug,
        service_url=args.service_url,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        advertise_host=args.advertise_host or args.listen_host,
        scheme=args.scheme,
        heartbeat_interval_seconds=args.heartbeat_interval,
        default_target_agent_slug=args.target,
    )
    await agent.start()
    try:
        await agent.run_repl()
    finally:
        await agent.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _build_arg_parser().parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
