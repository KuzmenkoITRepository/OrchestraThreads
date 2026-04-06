"""Manual CLI agent for exercising OrchestraThreads without an LLM runtime."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from core.orchestra_thread.client import OrchestraThreadsClient
from core.orchestra_thread.common import normalize_text_input

web = importlib.import_module("aiohttp.web")

JsonDict = dict[str, Any]
JsonObjectList = list[JsonDict]
CommandHandler = Callable[[Sequence[str]], Awaitable[bool]]


def _write_line(message: str) -> None:
    sys.stdout.write(f"{message}\n")


class ManualAgentCLI:  # noqa: WPS214, WPS230
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

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.advertise_host}:{self.listen_port}"

    async def start(self) -> None:
        self.thread_client = self.thread_client or OrchestraThreadsClient(
            base_url=self.service_url, timeout_seconds=10
        )
        await self._start_callback_server()
        await self._register()
        self.heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name=f"{self.agent_slug}-heartbeat"
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

    async def _start_callback_server(self) -> None:
        app = web.Application()
        app.router.add_post("/event", self._handle_event)
        app.router.add_post("/stop", self._handle_stop)
        app.router.add_get("/healthz", self._handle_health)
        runner = web.AppRunner(app)
        self.http_runner = runner
        await runner.setup()
        site = web.TCPSite(runner, host=self.listen_host, port=self.listen_port)
        await site.start()
        sockets = getattr(site, "_server", None)
        if sockets is not None and getattr(sockets, "sockets", None):
            bound_port = sockets.sockets[0].getsockname()[1]
            self.listen_port = int(bound_port)

    async def _register(self) -> dict[str, Any]:
        result = await self._require_client().register_agent(
            agent_slug=self.agent_slug,
            display_name=self.agent_slug,
            base_url=self.base_url,
            metadata={
                "kind": "manual-cli-agent",
                "argv": sys.argv,
            },
        )
        _write_line(
            f"[register] {self.agent_slug} -> {self.base_url} "
            f"(lease={result.get('agent_lease_seconds')}s)"
        )
        return result

    async def _heartbeat(self) -> None:
        try:
            await self._require_client().heartbeat(agent_slug=self.agent_slug)
        except Exception as exc:
            _write_line(f"[heartbeat-error] {exc}")

    async def _heartbeat_loop(self) -> None:
        while not self.shutdown_event.is_set():
            await asyncio.sleep(self.heartbeat_interval_seconds)
            if self.shutdown_event.is_set():
                return
            await self._heartbeat()

    async def _handle_health(self, _: Any) -> Any:
        return web.json_response(
            {
                "status": "ok",
                "agent_slug": self.agent_slug,
                "current_thread_id": self.current_thread_id,
            }
        )

    async def _handle_event(self, request: Any) -> Any:
        payload = await request.json()
        events = self._payload_items(payload, key="events")
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

    async def _handle_stop(self, request: Any) -> Any:
        payload = await request.json()
        self.stop_signals.append(payload)
        thread_id = str(payload.get("thread_id") or "").strip()
        _write_line(f"\n[stop] {json.dumps(payload, ensure_ascii=False)}")
        if thread_id and thread_id == self.current_thread_id:
            self.current_thread_id = None
        return web.json_response({"accepted": True})

    def _print_event(self, event: dict[str, Any]) -> None:
        preview = self._preview_message(event)
        if len(preview) > 160:
            preview = f"{preview[:157]}..."
        _write_line(
            "\n[event] "
            f"thread={event.get('thread_id')} "
            f"seq={event.get('sequence_no')} "
            f"kind={event.get('event_kind')} "
            f"status={event.get('notification_status') or '-'} "
            f"from={event.get('from_agent_slug')} "
            f"text={preview}"
        )

    async def _run_repl(self) -> None:
        self._print_help()
        while not self.shutdown_event.is_set():
            raw = (await self._read_repl_input()).strip()
            if not raw:
                continue
            should_stop = await self._dispatch_command_safe(raw)
            if should_stop:
                return

    async def _read_repl_input(self) -> str:
        try:
            return await asyncio.to_thread(input, f"{self._prompt()}> ")
        except EOFError:
            return "quit"

    async def _dispatch_command_safe(self, raw: str) -> bool:
        try:
            return await self._dispatch_command(raw)
        except Exception as exc:
            _write_line(f"[error] {exc}")
            return False

    def _prompt(self) -> str:
        current_peer = self.thread_peers.get(self.current_thread_id or "", None)
        if self.current_thread_id and current_peer:
            return f"[{self.agent_slug} -> {current_peer} #{self.current_thread_id[:8]}]"
        if self.default_target_agent_slug:
            return f"[{self.agent_slug} -> {self.default_target_agent_slug}]"
        return f"[{self.agent_slug}]"

    def _known_peer_for_current_thread(self) -> str | None:
        if not self.current_thread_id:
            return None
        return self.thread_peers.get(self.current_thread_id)

    def _peer_from_event(self, event: dict[str, Any]) -> str | None:
        thread_id = str(event.get("thread_id") or "").strip()
        from_agent_slug = str(event.get("from_agent_slug") or "").strip()
        to_agent_slug = str(event.get("to_agent_slug") or "").strip()
        if (
            from_agent_slug
            and from_agent_slug != self.agent_slug
            and from_agent_slug != "orchestra_threads"
        ):
            return from_agent_slug
        if (
            to_agent_slug
            and to_agent_slug != self.agent_slug
            and to_agent_slug != "orchestra_threads"
        ):
            return to_agent_slug
        if thread_id:
            return self.thread_peers.get(thread_id)
        return None

    async def _send_root_message(self, *, target: str, message: str) -> None:
        payload = await self._require_client().send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            message_text=message,
        )
        thread_id = self._payload_thread_id(payload)
        if thread_id:
            self.current_thread_id = thread_id
            self.thread_peers[thread_id] = target
        self.default_target_agent_slug = target
        self._print_message_ack(payload, target=target)

    async def _reply_current_thread(self, *, message: str) -> None:
        if not self.current_thread_id:
            raise RuntimeError("No current thread selected")
        target = self._known_peer_for_current_thread()
        if not target:
            raise RuntimeError(f"No known peer for thread {self.current_thread_id}")
        payload = await self._require_client().send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            thread_id=self.current_thread_id,
            message_text=message,
        )
        self.default_target_agent_slug = target
        self._print_message_ack(payload, target=target)

    async def _send_child_message(self, *, target: str, message: str) -> None:
        if not self.current_thread_id:
            raise RuntimeError("No current parent thread selected")
        payload = await self._require_client().send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            parent_thread_id=self.current_thread_id,
            message_text=message,
        )
        child_thread_id = self._payload_thread_id(payload)
        if child_thread_id:
            self.current_thread_id = child_thread_id
            self.thread_peers[child_thread_id] = target
        self.default_target_agent_slug = target
        self._print_message_ack(payload, target=target)

    async def _send_notification(self, *, status: str, message: str) -> None:
        if not self.current_thread_id:
            raise RuntimeError("No current thread selected")
        target = self._known_peer_for_current_thread()
        if not target:
            raise RuntimeError(f"No known peer for thread {self.current_thread_id}")
        payload = await self._require_client().send_notification(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target,
            thread_id=self.current_thread_id,
            status=status,
            message_text=message,
        )
        self._print_notification_ack(payload, target=target)

    def _print_message_ack(self, payload: dict[str, Any], *, target: str) -> None:
        thread = payload.get("thread") or {}
        _write_line(
            "[sent] "
            f"to={target} "
            f"thread={str(thread.get('thread_id') or '').strip() or '-'} "
            f"scope={str(thread.get('scope') or '').strip() or 'root'} "
            f"status={str(thread.get('status') or '').strip() or '-'} "
            f"route={'new' if payload.get('created_thread') else 'reused'}"
        )

    def _print_notification_ack(self, payload: dict[str, Any], *, target: str) -> None:
        thread = payload.get("thread") or {}
        event = payload.get("event") or {}
        _write_line(
            f"[status] to={target} thread={thread.get('thread_id')} "
            f"thread_status={thread.get('status')} published={event.get('notification_status')}"
        )

    def _print_threads(self, payload: dict[str, Any]) -> None:
        threads = self._payload_items(payload, key="threads")
        if not threads:
            _write_line("[threads] none")
            return
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            thread_id = str(thread.get("thread_id") or "").strip()
            peer = self._thread_peer(thread)
            marker = "*" if thread_id and thread_id == self.current_thread_id else " "
            _write_line(
                f"{marker} {thread_id} peer={peer or '?'} "
                f"status={thread.get('status')} scope={thread.get('scope')} owner={thread.get('owner_agent_slug')}"
            )

    def _thread_peer(self, thread: dict[str, Any]) -> str:
        participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
        participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
        return participant_b if participant_a == self.agent_slug else participant_a

    def _print_agents(self, payload: dict[str, Any]) -> None:
        agents = self._payload_items(payload, key="agents")
        if not agents:
            _write_line("[agents] none")
            return
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            _write_line(
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

    def _require_client(self) -> OrchestraThreadsClient:
        if self.thread_client is None:
            raise RuntimeError("HTTP client is not started")
        return self.thread_client

    async def _command_agents(self, _: Sequence[str]) -> bool:
        self._print_agents(await self._require_client().list_agents())
        return False

    async def _command_threads(self, parts: Sequence[str]) -> bool:
        scope = self._part_or_default(parts, index=1, default="active")
        self._print_threads(await self._require_client().list_threads(scope=scope))
        return False

    async def _command_thread(self, parts: Sequence[str]) -> bool:
        thread_id = self._part_or_none(parts, index=1) or self.current_thread_id
        if not thread_id:
            raise RuntimeError("No current thread. Use `thread <thread_id>` or `use <thread_id>`.")
        payload = await self._require_client().get_thread(thread_id=thread_id)
        _write_line(json.dumps(payload, ensure_ascii=False, indent=2))
        return False

    async def _command_use(self, parts: Sequence[str]) -> bool:
        if not self._has_exact_parts(parts, count=2):
            raise RuntimeError("Usage: use <thread_id>")
        self.current_thread_id = parts[1]
        peer = self.thread_peers.get(self.current_thread_id, "?")
        if peer and peer != "?":
            self.default_target_agent_slug = peer
        _write_line(f"[current] thread={self.current_thread_id} peer={peer}")
        return False

    async def _command_chat(self, parts: Sequence[str]) -> bool:
        if not self._has_exact_parts(parts, count=2):
            raise RuntimeError("Usage: chat <target_agent_slug>")
        target = parts[1].strip()
        self.default_target_agent_slug = target
        if self._known_peer_for_current_thread() not in {None, target}:
            self.current_thread_id = None
        _write_line(
            f"[chat] target={target} thread={self.current_thread_id or 'new-root-on-first-message'}"
        )
        return False

    async def _command_leave(self, _: Sequence[str]) -> bool:
        self.current_thread_id = None
        self.default_target_agent_slug = None
        _write_line("[chat] cleared current thread and target")
        return False

    async def _command_current(self, _: Sequence[str]) -> bool:
        _write_line(f"agent_slug={self.agent_slug}")
        _write_line(f"current_thread_id={self.current_thread_id}")
        _write_line(f"current_peer={self.thread_peers.get(self.current_thread_id or '', None)}")
        _write_line(f"default_target_agent_slug={self.default_target_agent_slug}")
        return False

    async def _command_inbox(self, parts: Sequence[str]) -> bool:
        limit = self._inbox_limit(parts)
        items = list(self.inbox)[-limit:]
        _write_line(json.dumps(items, ensure_ascii=False, indent=2))
        return False

    async def _command_send(self, parts: Sequence[str]) -> bool:
        if not self._has_min_parts(parts, minimum=3):
            raise RuntimeError('Usage: send <target_agent_slug> "<message>"')
        await self._send_root_message(
            target=parts[1], message=self._command_message(parts, start=2)
        )
        return False

    async def _command_reply(self, parts: Sequence[str]) -> bool:
        if not self._has_min_parts(parts, minimum=2):
            raise RuntimeError('Usage: reply "<message>"')
        await self._reply_current_thread(message=" ".join(parts[1:]))
        return False

    async def _command_child(self, parts: Sequence[str]) -> bool:
        if not self._has_min_parts(parts, minimum=3):
            raise RuntimeError('Usage: child <target_agent_slug> "<message>"')
        await self._send_child_message(
            target=parts[1], message=self._command_message(parts, start=2)
        )
        return False

    async def _command_notify(self, parts: Sequence[str]) -> bool:
        if not self._has_min_parts(parts, minimum=3):
            raise RuntimeError('Usage: notify <in_progress|review|done|closed> "<message>"')
        await self._send_notification(
            status=parts[1], message=self._command_message(parts, start=2)
        )
        return False

    async def _command_say(self, parts: Sequence[str]) -> bool:
        if not self._has_min_parts(parts, minimum=2):
            raise RuntimeError('Usage: say "<message>"')
        await self._handle_text_input(self._command_message(parts, start=1))
        return False

    @staticmethod
    def _payload_items(payload: JsonDict, *, key: str) -> JsonObjectList:
        items = payload.get(key)
        if not isinstance(items, list):
            return []
        dict_items: JsonObjectList = []
        for item in items:
            if isinstance(item, dict):
                dict_items.append(item)
        return dict_items

    @staticmethod
    def _payload_thread_id(payload: JsonDict) -> str:
        thread = payload.get("thread")
        if not isinstance(thread, dict):
            return ""
        return str(thread.get("thread_id") or "").strip()

    @staticmethod
    def _preview_message(event: dict[str, Any]) -> str:
        return " ".join(str(event.get("message_text") or "").split())

    def _inbox_limit(self, parts: Sequence[str]) -> int:
        if not self._has_min_parts(parts, minimum=2):
            return len(self.inbox)
        return max(1, int(self._part_or_default(parts, index=1, default="1")))

    @staticmethod
    def _part_or_default(parts: Sequence[str], *, index: int, default: str) -> str:
        return parts[index] if len(parts) > index else default

    @staticmethod
    def _part_or_none(parts: Sequence[str], *, index: int) -> str | None:
        return parts[index] if len(parts) > index else None

    @staticmethod
    def _has_exact_parts(parts: Sequence[str], *, count: int) -> bool:
        return len(parts) == count

    @staticmethod
    def _has_min_parts(parts: Sequence[str], *, minimum: int) -> bool:
        return len(parts) >= minimum

    @staticmethod
    def _command_message(parts: Sequence[str], *, start: int) -> str:
        return " ".join(parts[start:])

    def _command_handlers(self) -> dict[str, CommandHandler]:
        return {
            "agents": self._command_agents,
            "threads": self._command_threads,
            "thread": self._command_thread,
            "use": self._command_use,
            "chat": self._command_chat,
            "dm": self._command_chat,
            "leave": self._command_leave,
            "clear": self._command_leave,
            "current": self._command_current,
            "inbox": self._command_inbox,
            "send": self._command_send,
            "reply": self._command_reply,
            "child": self._command_child,
            "notify": self._command_notify,
            "say": self._command_say,
        }

    async def _dispatch_command(self, raw: str) -> bool:
        raw = normalize_text_input(raw).strip()
        if not raw:
            return False
        import shlex

        normalized_raw = raw[1:] if raw.startswith("/") else raw
        parts = shlex.split(normalized_raw)
        if not parts:
            return False
        return await self._run_command(parts=parts, raw=raw)

    async def _run_command(self, *, parts: Sequence[str], raw: str) -> bool:
        command = parts[0].lower()
        if command in {"quit", "exit"}:
            return True
        if command == "help":
            self._print_help()
            return False
        if command == "register":
            await self._register()
            return False
        handler = self._command_handlers().get(command)
        if handler is not None:
            return await handler(parts)
        if not await self._handle_text_input(raw):
            raise RuntimeError(f"Unknown command: {command}")
        return False

    async def _register_command(self, _: Sequence[str]) -> bool:
        await self._register()
        return False

    @staticmethod
    def _print_help() -> None:
        _write_line(
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
        await agent._run_repl()
    except Exception:
        await agent.stop()
        raise
    await agent.stop()


def main() -> None:
    args = _build_arg_parser().parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
