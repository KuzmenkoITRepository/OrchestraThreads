"""Command dispatch and send/reply flows for the manual CLI."""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable
from typing import Any

from core.orchestra_thread.agent_cli import output as cli_output
from core.orchestra_thread.agent_cli import state as cli_state
from core.orchestra_thread.common import normalize_text_input

_CommandHandler = Callable[[list[str]], Awaitable[bool]]
_TextInputHandler = Callable[[str], Awaitable[bool]]


class _CommandArgs:
    """Private parsing helpers for normalized command parts."""

    @classmethod
    def inbox_limit(cls, parts: list[str], *, inbox_size: int) -> int:
        raw_limit = cls._part_at(parts, 1)
        if raw_limit is None:
            return inbox_size
        return max(1, int(raw_limit))

    @classmethod
    def require_exact_arg(cls, parts: list[str], *, usage: str) -> str:
        argument = cls._part_at(parts, 1)
        if argument is None or cls._part_at(parts, 2) is not None:
            raise RuntimeError(f"Usage: {usage}")
        return argument

    @classmethod
    def require_message(cls, parts: list[str], *, usage: str) -> str:
        message = cls._joined_message(parts, start=1)
        if not message:
            raise RuntimeError(f"Usage: {usage}")
        return message

    @classmethod
    def require_target_and_message(cls, parts: list[str], *, usage: str) -> tuple[str, str]:
        target = cls._part_at(parts, 1)
        message = cls._joined_message(parts, start=2)
        if not target or not message:
            raise RuntimeError(f"Usage: {usage}")
        return target, message

    @classmethod
    def require_notification(cls, parts: list[str]) -> tuple[str, str]:
        usage = 'notify <in_progress|review|done|closed> "<message>"'
        status = cls._part_at(parts, 1)
        message = cls._joined_message(parts, start=2)
        if not status or not message:
            raise RuntimeError(f"Usage: {usage}")
        return status, message

    @staticmethod
    def _part_at(parts: list[str], index: int) -> str | None:
        if index >= len(parts):
            return None
        return parts[index]

    @staticmethod
    def _joined_message(parts: list[str], *, start: int) -> str:
        return " ".join(parts[start:])


class MessageCommands:
    """Message and notification sending flows."""

    def __init__(self, cli: Any) -> None:
        self._cli = cli

    async def send_root(self, *, target: str, message: str) -> None:
        """Create or reuse a root thread for a direct message."""
        payload = await cli_state.require_client(self._cli.thread_client).send_message(
            from_agent_slug=self._cli.agent_slug,
            to_agent_slug=target,
            message_text=message,
        )
        thread_id = cli_state.payload_thread_id(payload)
        if thread_id:
            self._cli.current_thread_id = thread_id
            self._cli.thread_peers[thread_id] = target
        self._cli.default_target_agent_slug = target
        cli_output.OutputFormatter.print_message_ack(payload, target=target)

    async def reply_current(self, *, message: str) -> None:
        """Reply inside the current thread."""
        thread_id = self._cli.current_thread_id
        if not thread_id:
            raise RuntimeError("No current thread selected")

        target = cli_state.known_peer_for_thread(thread_id, self._cli.thread_peers)
        if not target:
            raise RuntimeError(f"No known peer for thread {thread_id}")

        payload = await cli_state.require_client(self._cli.thread_client).send_message(
            from_agent_slug=self._cli.agent_slug,
            to_agent_slug=target,
            thread_id=thread_id,
            message_text=message,
        )
        self._cli.default_target_agent_slug = target
        cli_output.OutputFormatter.print_message_ack(payload, target=target)

    async def send_child(self, *, target: str, message: str) -> None:
        """Create a child thread from the current thread."""
        parent_thread_id = self._cli.current_thread_id
        if not parent_thread_id:
            raise RuntimeError("No current parent thread selected")

        payload = await cli_state.require_client(self._cli.thread_client).send_message(
            from_agent_slug=self._cli.agent_slug,
            to_agent_slug=target,
            parent_thread_id=parent_thread_id,
            message_text=message,
        )
        child_thread_id = cli_state.payload_thread_id(payload)
        if child_thread_id:
            self._cli.current_thread_id = child_thread_id
            self._cli.thread_peers[child_thread_id] = target
        self._cli.default_target_agent_slug = target
        cli_output.OutputFormatter.print_message_ack(payload, target=target)

    async def send_notification(self, *, status: str, message: str) -> None:
        """Publish a notification into the current thread."""
        thread_id = self._cli.current_thread_id
        if not thread_id:
            raise RuntimeError("No current thread selected")

        target = cli_state.known_peer_for_thread(thread_id, self._cli.thread_peers)
        if not target:
            raise RuntimeError(f"No known peer for thread {thread_id}")

        payload = await cli_state.require_client(self._cli.thread_client).send_notification(
            from_agent_slug=self._cli.agent_slug,
            to_agent_slug=target,
            thread_id=thread_id,
            status=status,
            message_text=message,
        )
        cli_output.OutputFormatter.print_notification_ack(payload, target=target)


class ListingCommands:
    """Read-only list and inspection commands."""

    def __init__(self, cli: Any) -> None:
        self._cli = cli

    async def agents(self, _: list[str]) -> bool:
        """Show registered agents."""
        cli_output.OutputFormatter.print_agents(
            await cli_state.require_client(self._cli.thread_client).list_agents(),
        )
        return False

    async def threads(self, parts: list[str]) -> bool:
        """Show available threads."""
        scope = _CommandArgs._part_at(parts, 1) or "active"
        payload = await cli_state.require_client(self._cli.thread_client).list_threads(scope=scope)
        cli_output.OutputFormatter.print_threads(
            payload,
            agent_slug=self._cli.agent_slug,
            current_thread_id=self._cli.current_thread_id,
        )
        return False

    async def thread(self, parts: list[str]) -> bool:
        """Show one thread payload."""
        thread_id = _CommandArgs._part_at(parts, 1) or self._cli.current_thread_id
        if not thread_id:
            raise RuntimeError("No current thread. Use `thread <thread_id>` or `use <thread_id>`.")
        payload = await cli_state.require_client(self._cli.thread_client).get_thread(
            thread_id=thread_id
        )
        cli_output.OutputWriter.print_json(payload)
        return False

    async def inbox(self, parts: list[str]) -> bool:
        """Show recent delivered events."""
        limit = _CommandArgs.inbox_limit(parts, inbox_size=len(self._cli.inbox))
        cli_output.OutputWriter.print_json(list(self._cli.inbox)[-limit:])
        return False


class ContextCommands:
    """Chat-target and current-thread selection commands."""

    def __init__(self, cli: Any) -> None:
        self._cli = cli

    async def use(self, parts: list[str]) -> bool:
        """Select the active thread."""
        self._cli.current_thread_id = _CommandArgs.require_exact_arg(
            parts,
            usage="use <thread_id>",
        )
        peer = self._cli.thread_peers.get(self._cli.current_thread_id, "?")
        if peer != "?":
            self._cli.default_target_agent_slug = peer
        cli_output.OutputWriter.write_line(
            f"[current] thread={self._cli.current_thread_id} peer={peer}"
        )
        return False

    async def chat(self, parts: list[str]) -> bool:
        """Select a default chat peer."""
        target = _CommandArgs.require_exact_arg(parts, usage="chat <target_agent_slug>").strip()
        self._cli.default_target_agent_slug = target
        current_peer = cli_state.known_peer_for_thread(
            self._cli.current_thread_id,
            self._cli.thread_peers,
        )
        if current_peer not in {None, target}:
            self._cli.current_thread_id = None
        cli_output.OutputWriter.write_line(
            f"[chat] target={target} "
            f"thread={self._cli.current_thread_id or 'new-root-on-first-message'}"
        )
        return False

    async def leave(self, _: list[str]) -> bool:
        """Clear the current target and thread selection."""
        self._cli.current_thread_id = None
        self._cli.default_target_agent_slug = None
        cli_output.OutputWriter.write_line("[chat] cleared current thread and target")
        return False

    async def current(self, _: list[str]) -> bool:
        """Show the current chat selection state."""
        cli_output.OutputWriter.print_current(
            agent_slug=self._cli.agent_slug,
            current_thread_id=self._cli.current_thread_id,
            default_target_agent_slug=self._cli.default_target_agent_slug,
            thread_peers=self._cli.thread_peers,
        )
        return False


class ActionCommands:
    """Named command handlers that orchestrate collaborators."""

    def __init__(self, cli: Any, *, handle_text_input: _TextInputHandler) -> None:
        self._cli = cli
        self._handle_text_input = handle_text_input
        self._messages = MessageCommands(cli)

    async def register(self, _: list[str]) -> bool:
        """Register the agent again on demand."""
        await self._cli._callback_lifecycle.register()
        return False

    async def send(self, parts: list[str]) -> bool:
        """Send a new root message."""
        target, message = _CommandArgs.require_target_and_message(
            parts, usage='send <target_agent_slug> "<message>"'
        )
        await self._messages.send_root(target=target, message=message)
        return False

    async def reply(self, parts: list[str]) -> bool:
        """Reply into the current thread."""
        await self._messages.reply_current(
            message=_CommandArgs.require_message(parts, usage='reply "<message>"'),
        )
        return False

    async def child(self, parts: list[str]) -> bool:
        """Create a child-thread message."""
        target, message = _CommandArgs.require_target_and_message(
            parts, usage='child <target_agent_slug> "<message>"'
        )
        await self._messages.send_child(target=target, message=message)
        return False

    async def notify(self, parts: list[str]) -> bool:
        """Send a thread notification."""
        status, message = _CommandArgs.require_notification(parts)
        await self._messages.send_notification(status=status, message=message)
        return False

    async def say(self, parts: list[str]) -> bool:
        """Treat quoted text as plain chat input."""
        await self._handle_text_input(
            _CommandArgs.require_message(parts, usage='say "<message>"'),
        )
        return False


class CommandRouter:
    """Normalize REPL input and dispatch it to role-specific handlers."""

    def __init__(self, cli: Any) -> None:
        self._cli = cli
        self._actions = ActionCommands(cli, handle_text_input=self.handle_text_input)
        self._listing = ListingCommands(cli)
        self._context = ContextCommands(cli)
        self._messages = self._actions._messages

    async def dispatch(self, raw: str) -> bool:
        """Normalize raw input and route it to the right command flow."""
        normalized = normalize_text_input(raw).strip()
        if not normalized:
            return False
        command_line = normalized[1:] if normalized.startswith("/") else normalized
        parts = shlex.split(command_line)
        if not parts:
            return False
        return await self._run_command(parts, raw=raw)

    async def handle_text_input(self, raw: str) -> bool:
        """Handle plain chat input outside explicit slash commands."""
        message = normalize_text_input(raw).strip()
        if not message:
            return False
        if message.startswith("@"):
            prefix, _, body = message.partition(" ")
            target = prefix[1:].strip()
            if not target or not body.strip():
                raise RuntimeError("Usage: @<target_agent_slug> <message>")
            await self._messages.send_root(target=target, message=body.strip())
            return True

        current_peer = cli_state.known_peer_for_thread(
            self._cli.current_thread_id,
            self._cli.thread_peers,
        )
        if self._cli.current_thread_id and current_peer:
            await self._messages.reply_current(message=message)
            return True
        if self._cli.default_target_agent_slug:
            await self._messages.send_root(
                target=self._cli.default_target_agent_slug,
                message=message,
            )
            return True
        raise RuntimeError("No chat target selected. Use `chat <agent_slug>` or `@agent message`.")

    async def _run_command(self, parts: list[str], *, raw: str) -> bool:
        command = parts[0].lower()
        if command in {"quit", "exit"}:
            return True
        if command == "help":
            cli_output.OutputWriter.print_help()
            return False

        handler = self._command_handlers().get(command)
        if handler is not None:
            return await handler(parts)
        if not await self.handle_text_input(raw):
            raise RuntimeError(f"Unknown command: {command}")
        return False

    def _command_handlers(self) -> dict[str, _CommandHandler]:
        return {
            "register": self._actions.register,
            "agents": self._listing.agents,
            "threads": self._listing.threads,
            "thread": self._listing.thread,
            "use": self._context.use,
            "chat": self._context.chat,
            "dm": self._context.chat,
            "leave": self._context.leave,
            "clear": self._context.leave,
            "current": self._context.current,
            "inbox": self._listing.inbox,
            "send": self._actions.send,
            "reply": self._actions.reply,
            "child": self._actions.child,
            "notify": self._actions.notify,
            "say": self._actions.say,
        }
