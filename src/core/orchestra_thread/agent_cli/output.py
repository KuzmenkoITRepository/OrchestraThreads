"""Output and formatting helpers for the manual agent CLI."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

from core.orchestra_thread.agent_cli import state as cli_state

_help_lines = (
    "Commands:",
    "  help",
    "  register",
    "  agents",
    "  threads [active|all]",
    "  thread [thread_id]",
    "  chat <target_agent_slug>",
    "  leave",
    "  use <thread_id>",
    "  current",
    "  inbox [limit]",
    "  @<target_agent_slug> <message>",
    '  say "<message>"',
    '  send <target_agent_slug> "<message>"',
    '  reply "<message>"',
    '  child <target_agent_slug> "<message>"',
    '  notify <in_progress|review|done|closed> "<message>"',
    "  /<command>        # optional slash-prefix for commands",
    "  <message>         # send to current thread or selected chat target",
    "  quit",
)
_preview_limit = 160


class OutputWriter:
    """Simple stdout writer helpers for the CLI."""

    @classmethod
    def write_line(cls, message: str) -> None:
        """Write a single line to stdout."""
        sys.stdout.write(f"{message}\n")

    @classmethod
    def print_help(cls) -> None:
        """Show the supported REPL commands."""
        cls.write_line("\n".join(_help_lines))

    @classmethod
    def print_json(cls, payload: Any) -> None:
        """Render structured payloads as indented JSON."""
        cls.write_line(json.dumps(payload, ensure_ascii=False, indent=2))

    @classmethod
    def print_current(
        cls,
        *,
        agent_slug: str,
        current_thread_id: str | None,
        default_target_agent_slug: str | None,
        thread_peers: Mapping[str, str],
    ) -> None:
        """Render the current CLI chat state."""
        cls.write_line(f"agent_slug={agent_slug}")
        cls.write_line(f"current_thread_id={current_thread_id}")
        cls.write_line(f"current_peer={thread_peers.get(current_thread_id or '', None)}")
        cls.write_line(f"default_target_agent_slug={default_target_agent_slug}")


class OutputHelpers:
    """Small formatting helpers shared by output renderers."""

    @classmethod
    def event_preview(cls, event: Mapping[str, object]) -> str:
        """Return a bounded one-line message preview."""
        preview = cls._normalized_message_text(event)
        if len(preview) <= _preview_limit:
            return preview
        return f"{preview[: _preview_limit - 3]}..."

    @staticmethod
    def payload_dict(payload: Mapping[str, object], *, key: str) -> dict[str, object]:
        """Return a dict payload section or an empty dict."""
        item = payload.get(key)
        if isinstance(item, dict):
            return item
        return {}

    @staticmethod
    def _normalized_message_text(event: Mapping[str, object]) -> str:
        raw_text = str(event.get("message_text") or "")
        return " ".join(raw_text.split())


class OutputFormatter:
    """Human-readable output formatting for CLI workflows."""

    @staticmethod
    def format_prompt(
        *,
        agent_slug: str,
        current_thread_id: str | None,
        default_target_agent_slug: str | None,
        thread_peers: Mapping[str, str],
    ) -> str:
        """Build the interactive prompt for the current chat context."""
        current_peer = thread_peers.get(current_thread_id or "")
        if current_thread_id and current_peer:
            return f"[{agent_slug} -> {current_peer} #{current_thread_id[:8]}]"
        if default_target_agent_slug:
            return f"[{agent_slug} -> {default_target_agent_slug}]"
        return f"[{agent_slug}]"

    @classmethod
    def print_event(cls, event: Mapping[str, object]) -> None:
        """Render an incoming event summary to stdout."""
        OutputWriter.write_line(
            "\n[event] "
            f"thread={event.get('thread_id')} "
            f"seq={event.get('sequence_no')} "
            f"kind={event.get('event_kind')} "
            f"status={event.get('notification_status') or '-'} "
            f"from={event.get('from_agent_slug')} "
            f"text={OutputHelpers.event_preview(event)}"
        )

    @classmethod
    def print_message_ack(cls, payload: Mapping[str, object], *, target: str) -> None:
        """Render the ack for a sent message."""
        thread = OutputHelpers.payload_dict(payload, key="thread")
        OutputWriter.write_line(
            "[sent] "
            f"to={target} "
            f"thread={str(thread.get('thread_id') or '').strip() or '-'} "
            f"scope={str(thread.get('scope') or '').strip() or 'root'} "
            f"status={str(thread.get('status') or '').strip() or '-'} "
            f"route={'new' if payload.get('created_thread') else 'reused'}"
        )

    @classmethod
    def print_notification_ack(cls, payload: Mapping[str, object], *, target: str) -> None:
        """Render the ack for a sent notification."""
        thread = OutputHelpers.payload_dict(payload, key="thread")
        event = OutputHelpers.payload_dict(payload, key="event")
        OutputWriter.write_line(
            f"[status] to={target} thread={thread.get('thread_id')} "
            f"thread_status={thread.get('status')} "
            f"published={event.get('notification_status')}"
        )

    @classmethod
    def print_threads(
        cls,
        payload: Mapping[str, object],
        *,
        agent_slug: str,
        current_thread_id: str | None,
    ) -> None:
        """Render thread list output."""
        threads = cli_state.payload_items(payload, key="threads")
        if not threads:
            OutputWriter.write_line("[threads] none")
            return

        for thread in threads:
            thread_id = str(thread.get("thread_id") or "").strip()
            marker = "*" if thread_id and thread_id == current_thread_id else " "
            peer = cli_state.thread_peer(thread, agent_slug=agent_slug) or "?"
            OutputWriter.write_line(
                f"{marker} {thread_id} peer={peer} status={thread.get('status')} "
                f"scope={thread.get('scope')} owner={thread.get('owner_agent_slug')}"
            )

    @classmethod
    def print_agents(cls, payload: Mapping[str, object]) -> None:
        """Render agent list output."""
        agents = cli_state.payload_items(payload, key="agents")
        if not agents:
            OutputWriter.write_line("[agents] none")
            return

        for agent in agents:
            OutputWriter.write_line(
                f"{agent.get('agent_slug')} online={agent.get('online')} "
                f"last_seen_at={agent.get('last_seen_at')} "
                f"base_url={agent.get('event_callback_url')}"
            )
