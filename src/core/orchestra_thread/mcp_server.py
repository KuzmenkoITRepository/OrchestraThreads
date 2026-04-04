"""Compact MCP server for OrchestraThreads.

This server is intentionally narrow:
- routing defaults come from active invocation context;
- tool responses are compact-by-default;
- full thread inspection is opt-in through `thread_expand`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional

from .active_context import read_active_context
from .client import OrchestraThreadsClient


logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"


def _normalize_optional_str(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return normalized


def _peer_from_thread(thread: dict[str, Any], agent_slug: str) -> str:
    participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
    participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
    if agent_slug == participant_a:
        return participant_b
    if agent_slug == participant_b:
        return participant_a
    raise RuntimeError(f"{agent_slug} is not a participant of thread {thread.get('thread_id')}")


class OrchestraThreadsMCPServer:
    """Small JSON-RPC MCP server over stdio for future real-agent integration."""

    def __init__(
        self,
        *,
        agent_slug: Optional[str] = None,
        client: Optional[OrchestraThreadsClient] = None,
    ) -> None:
        self.agent_slug = _normalize_optional_str(
            agent_slug
            or os.getenv("ORCHESTRA_THREADS_AGENT_SLUG")
            or os.getenv("AGENT_SLUG")
        )
        if not self.agent_slug:
            raise RuntimeError("ORCHESTRA_THREADS_AGENT_SLUG or AGENT_SLUG is required")
        self.client = client or OrchestraThreadsClient()

    async def close(self) -> None:
        await self.client.close()

    def _result(self, payload: dict[str, Any], *, text: Optional[str] = None) -> dict[str, Any]:
        return {
            "structuredContent": payload,
            "content": [
                {
                    "type": "text",
                    "text": text or json.dumps(payload, ensure_ascii=False),
                }
            ],
        }

    @staticmethod
    def _tool(name: str, description: str, input_schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }

    def _active_context(self) -> dict[str, Any]:
        return read_active_context()

    def _resolve_send_routing(
        self,
        *,
        target_agent_slug: Optional[str],
        mode: str,
        explicit_thread_id: Optional[str],
    ) -> tuple[Optional[str], Optional[str], str, str]:
        context = self._active_context()
        current_thread_id = _normalize_optional_str(context.get("thread_id"))
        source_agent_slug = _normalize_optional_str(context.get("source_agent_slug"))
        normalized_target = _normalize_optional_str(target_agent_slug)
        normalized_mode = str(mode or "auto").strip().lower() or "auto"

        if normalized_mode not in {"auto", "root", "child", "exact"}:
            raise RuntimeError("mode must be one of auto, root, child, exact")

        if normalized_mode == "exact":
            thread_id = explicit_thread_id or current_thread_id
            if not thread_id:
                raise RuntimeError("thread_id is required for mode=exact")
            resolved_target = normalized_target or source_agent_slug
            if not resolved_target:
                raise RuntimeError("target_agent_slug is required when no active peer is known")
            return thread_id, None, resolved_target, "exact_thread"

        if normalized_mode == "root":
            if not normalized_target:
                raise RuntimeError("target_agent_slug is required for mode=root")
            return None, None, normalized_target, "root"

        if normalized_mode == "child":
            if not current_thread_id:
                raise RuntimeError("mode=child requires an active thread context")
            if not normalized_target:
                raise RuntimeError("target_agent_slug is required for mode=child")
            return None, current_thread_id, normalized_target, "child"

        if current_thread_id:
            if not normalized_target and source_agent_slug:
                return current_thread_id, None, source_agent_slug, "reply_current"
            if normalized_target and source_agent_slug and normalized_target == source_agent_slug:
                return current_thread_id, None, normalized_target, "reply_current"
            if normalized_target:
                return None, current_thread_id, normalized_target, "child"
            raise RuntimeError("target_agent_slug is required when auto routing has no known source peer")

        if not normalized_target:
            raise RuntimeError("target_agent_slug is required outside an active thread")
        return None, None, normalized_target, "root"

    async def _thread_send(self, arguments: dict[str, Any]) -> dict[str, Any]:
        message = _ensure_text(arguments.get("message"), field_name="message")
        target_agent_slug = _normalize_optional_str(arguments.get("target_agent_slug"))
        explicit_thread_id = _normalize_optional_str(arguments.get("thread_id"))
        thread_id, parent_thread_id, resolved_target, route = self._resolve_send_routing(
            target_agent_slug=target_agent_slug,
            mode=str(arguments.get("mode") or "auto"),
            explicit_thread_id=explicit_thread_id,
        )
        payload = await self.client.send_message(
            from_agent_slug=self.agent_slug,
            to_agent_slug=resolved_target,
            message_text=message,
            thread_id=thread_id,
            parent_thread_id=parent_thread_id,
            client_request_id=_normalize_optional_str(arguments.get("client_request_id")),
        )
        thread = payload.get("thread") or {}
        created_thread = bool(payload.get("created_thread"))
        compact_route = route
        if route == "root":
            compact_route = "created_root" if created_thread else "reused_root"
        elif route == "child":
            compact_route = "created_child" if created_thread else "reused_child"
        return self._result(
            {
                "ok": True,
                "operation": "thread_send",
                "route": compact_route,
                "thread_id": thread.get("thread_id"),
                "root_thread_id": thread.get("root_thread_id"),
                "parent_thread_id": thread.get("parent_thread_id"),
                "status": thread.get("status"),
                "peer_agent_slug": resolved_target,
                "created_thread": created_thread,
            }
        )

    async def _thread_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._active_context()
        thread_id = _normalize_optional_str(arguments.get("thread_id")) or _normalize_optional_str(context.get("thread_id"))
        if not thread_id:
            raise RuntimeError("thread_id is required outside an active thread")
        target_agent_slug = _normalize_optional_str(arguments.get("target_agent_slug")) or _normalize_optional_str(
            context.get("source_agent_slug")
        )
        status = _ensure_text(arguments.get("status"), field_name="status")
        message = _ensure_text(arguments.get("message"), field_name="message")
        if not target_agent_slug:
            compact = await self.client.get_thread_compact(thread_id=thread_id)
            target_agent_slug = _peer_from_thread(compact.get("thread") or {}, self.agent_slug)
        payload = await self.client.send_notification(
            from_agent_slug=self.agent_slug,
            to_agent_slug=target_agent_slug,
            thread_id=thread_id,
            status=status,
            message_text=message,
            client_request_id=_normalize_optional_str(arguments.get("client_request_id")),
        )
        thread = payload.get("thread") or {}
        return self._result(
            {
                "ok": True,
                "operation": "thread_status",
                "thread_id": thread.get("thread_id"),
                "status": thread.get("status"),
                "published_status": status.lower(),
                "peer_agent_slug": target_agent_slug,
                "terminal": status.lower() in {"done", "closed"},
                "delivered": status.lower() in {"in_progress", "review"},
            }
        )

    async def _thread_current(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._active_context()
        thread_id = _normalize_optional_str(arguments.get("thread_id")) or _normalize_optional_str(context.get("thread_id"))
        if not thread_id:
            return self._result(
                {
                    "ok": True,
                    "active": False,
                    "thread_id": None,
                    "summary": "No active thread in invocation context.",
                }
            )
        compact_payload = await self.client.get_thread_compact(thread_id=thread_id)
        thread = compact_payload.get("thread") or {}
        peer_agent_slug = _peer_from_thread(thread, self.agent_slug)
        last_event_kind = _normalize_optional_str(thread.get("last_event_kind")) or "none"
        last_event_from = _normalize_optional_str(thread.get("last_event_from_agent_slug"))
        last_event_to = _normalize_optional_str(thread.get("last_event_to_agent_slug"))
        waiting_on: Optional[str] = None
        if last_event_kind in {"message", "inactive"}:
            waiting_on = last_event_to
        elif last_event_kind == "notification":
            notification_status = _normalize_optional_str(thread.get("last_event_notification_status"))
            if notification_status == "review":
                waiting_on = _normalize_optional_str(thread.get("owner_agent_slug"))
        if str(thread.get("status") or "").strip().lower() in {"done", "closed"}:
            allowed_actions: list[str] = []
        elif self.agent_slug == str(thread.get("owner_agent_slug") or "").strip():
            allowed_actions = ["thread_send", "thread_status:in_progress", "thread_status:done", "thread_status:closed"]
        else:
            allowed_actions = ["thread_send", "thread_status:in_progress", "thread_status:review"]

        preview = str(thread.get("last_event_message_preview") or "").strip()
        summary = "No events yet."
        if last_event_kind == "message":
            summary = f"{last_event_from} asked: {preview}"
        elif last_event_kind == "notification":
            notification_status = _normalize_optional_str(thread.get("last_event_notification_status")) or "notification"
            summary = f"{last_event_from} sent {notification_status}: {preview}"
        elif last_event_kind == "inactive":
            summary = f"Inactivity wake-up for {last_event_to}: {preview}"

        return self._result(
            {
                "ok": True,
                "active": True,
                "thread_id": thread.get("thread_id"),
                "root_thread_id": thread.get("root_thread_id"),
                "parent_thread_id": thread.get("parent_thread_id"),
                "scope": thread.get("scope"),
                "status": thread.get("status"),
                "owner_agent_slug": thread.get("owner_agent_slug"),
                "peer_agent_slug": peer_agent_slug,
                "waiting_on": waiting_on,
                "last_event_kind": last_event_kind,
                "last_message_from": last_event_from,
                "summary": summary,
                "allowed_actions": allowed_actions,
            }
        )

    async def _thread_expand(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._active_context()
        thread_id = _normalize_optional_str(arguments.get("thread_id")) or _normalize_optional_str(context.get("thread_id"))
        if not thread_id:
            raise RuntimeError("thread_id is required outside an active thread")
        view = str(arguments.get("view") or "latest").strip().lower() or "latest"
        limit = int(arguments.get("limit") or 5)
        payload = await self.client.get_thread(thread_id=thread_id, limit=max(1, min(limit, 200)))
        events = payload.get("events") or []
        if view == "latest":
            result = {
                "ok": True,
                "thread": payload.get("thread"),
                "latest_event": events[-1] if events else None,
            }
        elif view == "tail":
            result = {
                "ok": True,
                "thread": payload.get("thread"),
                "events": events[-max(1, min(limit, len(events) or 1)):],
            }
        elif view == "related":
            result = {
                "ok": True,
                "thread": payload.get("thread"),
                "related": payload.get("related"),
            }
        elif view == "full":
            result = payload
        else:
            raise RuntimeError("view must be one of latest, tail, related, full")
        return self._result(result)

    async def _thread_guide(self, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = await self.client.get_instruction(
            view=str(arguments.get("view") or "compact"),
            section=_normalize_optional_str(arguments.get("section")),
        )
        instruction = payload.get("instruction") or {}
        text = str(instruction.get("text") or "").strip() or json.dumps(instruction, ensure_ascii=False)
        structured = {
            "ok": True,
            "operation": "thread_guide",
            **{key: value for key, value in instruction.items() if key != "text"},
        }
        return self._result(structured, text=text)

    def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {
                "name": "orchestra-threads-mcp",
                "version": "0.1.0",
            },
        }

    @staticmethod
    def handle_resources_list() -> dict[str, Any]:
        return {"resources": []}

    @staticmethod
    def handle_resource_templates_list() -> dict[str, Any]:
        return {"resourceTemplates": []}

    def handle_tools_list(self) -> dict[str, Any]:
        return {
            "tools": [
                self._tool(
                    "thread_send",
                    "Send a thread message using compact auto-routing based on the active invocation context.",
                    {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "target_agent_slug": {"type": "string"},
                            "mode": {
                                "type": "string",
                                "enum": ["auto", "root", "child", "exact"],
                            },
                            "thread_id": {"type": "string"},
                            "client_request_id": {"type": "string"},
                        },
                        "required": ["message"],
                    },
                ),
                self._tool(
                    "thread_status",
                    "Publish thread status updates without repeating thread_id when an active context exists.",
                    {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["in_progress", "review", "done", "closed"],
                            },
                            "message": {"type": "string"},
                            "thread_id": {"type": "string"},
                            "target_agent_slug": {"type": "string"},
                            "client_request_id": {"type": "string"},
                        },
                        "required": ["status", "message"],
                    },
                ),
                self._tool(
                    "thread_current",
                    "Return compact current-thread state for the active invocation.",
                    {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                        },
                    },
                ),
                self._tool(
                    "thread_expand",
                    "Expand thread details on demand. Use sparingly when compact state is insufficient.",
                    {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                            "view": {
                                "type": "string",
                                "enum": ["latest", "tail", "related", "full"],
                            },
                            "limit": {"type": "integer"},
                        },
                    },
                ),
                self._tool(
                    "thread_guide",
                    "Fetch the canonical OrchestraThreads workflow and routing/status rules from the service.",
                    {
                        "type": "object",
                        "properties": {
                            "view": {
                                "type": "string",
                                "enum": ["compact", "full"],
                            },
                            "section": {
                                "type": "string",
                                "enum": ["overview", "workflow", "routing", "statuses", "delivery", "mcp", "mcp_tools"],
                            },
                        },
                    },
                ),
            ]
        }

    async def handle_tools_call(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "thread_send":
            return await self._thread_send(arguments)
        if name == "thread_status":
            return await self._thread_status(arguments)
        if name == "thread_current":
            return await self._thread_current(arguments)
        if name == "thread_expand":
            return await self._thread_expand(arguments)
        if name == "thread_guide":
            return await self._thread_guide(arguments)
        raise RuntimeError(f"Unknown tool: {name}")

    async def handle_request(self, request: dict[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})
        if request_id is None:
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": self.handle_initialize(params)}
        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": self.handle_resources_list()}
        if method == "resources/templates/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": self.handle_resource_templates_list()}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": self.handle_tools_list()}
        if method == "tools/call":
            try:
                result = await self.handle_tools_call(
                    name=str(params.get("name") or ""),
                    arguments=params.get("arguments") if isinstance(params.get("arguments"), dict) else {},
                )
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as exc:
                logger.error("MCP tool failed: %s", exc, exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def _encode_message(payload: dict[str, Any], *, framing: str) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "content_length":
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body
    return body + b"\n"


async def _read_message(reader, *, framing_hint: Optional[str] = None) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if framing_hint == "content_length":
        return await _read_content_length_message(reader), "content_length"
    if framing_hint == "newline":
        return await _read_newline_message(reader), "newline"

    first_byte = await asyncio.to_thread(reader.read, 1)
    if not first_byte:
        return None, None
    if first_byte in b"{[":
        return await _read_newline_message(reader, first_chunk=first_byte), "newline"
    return await _read_content_length_message(reader, first_chunk=first_byte), "content_length"


async def _read_newline_message(reader, *, first_chunk: bytes = b"") -> Optional[dict[str, Any]]:
    line = first_chunk + await asyncio.to_thread(reader.readline)
    if not line:
        return None
    return json.loads(line.decode("utf-8").strip())


async def _read_content_length_message(reader, *, first_chunk: bytes = b"") -> Optional[dict[str, Any]]:
    header_bytes = bytes(first_chunk)
    while True:
        chunk = await asyncio.to_thread(reader.read, 1)
        if not chunk:
            return None
        header_bytes += chunk
        if header_bytes.endswith(b"\r\n\r\n"):
            break
    content_length = None
    for raw_line in header_bytes.decode("ascii").split("\r\n"):
        if raw_line.lower().startswith("content-length:"):
            content_length = int(raw_line.split(":", 1)[1].strip())
            break
    if content_length is None:
        raise RuntimeError("Missing Content-Length header")
    body = await asyncio.to_thread(reader.read, content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


async def main_async() -> None:
    server = OrchestraThreadsMCPServer()
    framing: Optional[str] = None
    try:
        while True:
            request, framing = await _read_message(sys.stdin.buffer, framing_hint=framing)
            if request is None:
                break
            response = await server.handle_request(request)
            if response is not None:
                sys.stdout.buffer.write(_encode_message(response, framing=framing or "newline"))
                sys.stdout.buffer.flush()
    finally:
        await server.close()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
