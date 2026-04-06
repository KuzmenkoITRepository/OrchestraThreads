"""Canonical service guide returned by OrchestraThreads and reused by MCP."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

GUIDE_ID = "orchestra_threads_mvp"
GUIDE_VERSION = "mvp-1"

_FULL_GUIDE: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "instruction_id": GUIDE_ID,
        "service": "orchestra_threads",
        "version": GUIDE_VERSION,
        "summary": (
            "Use thread_current to inspect active work, thread_send to reply or delegate, "
            "thread_status for lifecycle updates, and thread_expand only when compact state "
            "is insufficient."
        ),
        "workflow": (
            "If there is an active invocation, call thread_current first.",
            "Reply to the current peer with thread_send(message).",
            "Sending to a different target creates or reuses a child thread.",
            "Outside an active thread, thread_send creates or reuses the root pair thread.",
            "Use thread_status for in_progress, review, done, or closed updates.",
            "Use thread_expand only when compact state is insufficient.",
        ),
        "routing_rules": (
            "Explicit thread_id continues that exact thread.",
            "Explicit parent_thread_id creates or reuses a child thread under that parent.",
            "No thread_id and no parent_thread_id create or reuse the active root thread.",
            "In MCP auto mode, replying stays in the current thread; different target creates child.",
        ),
        "status_rules": (
            "Statuses are open, in_progress, review, done, and closed.",
            "The owner can publish in_progress, done, and closed.",
            "The peer can publish in_progress and review.",
            "done and closed are terminal. closed triggers /stop on the peer.",
        ),
        "delivery_rules": (
            "message, in_progress, review, and inactive are delivered through /event.",
            "done and closed do not wake the peer through /event.",
            "Delivery is at-least-once with retry and backoff.",
            "Terminal parent threads cascade-close live child threads.",
        ),
        "recommended_mcp_tool_flow": (
            "Call thread_current when you need to understand the active thread.",
            "Use thread_send to reply in the current thread or delegate.",
            "Use thread_status to publish progress, review, done, or closed.",
            "Use thread_expand only for details not in compact state.",
            "Use thread_guide when you need to refresh the service rules.",
        ),
        "mcp_tools": (
            "thread_current: fetch compact current-thread state from active context.",
            "thread_send: reply in the current thread or route to a root or child thread.",
            "thread_status: publish in_progress, review, done, or closed.",
            "thread_expand: inspect latest, tail, related, or full thread data on demand.",
            "thread_guide: fetch the canonical OrchestraThreads workflow and rules.",
        ),
    }
)

_SECTION_ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "overview": "overview",
        "workflow": "workflow",
        "routing": "routing_rules",
        "routing_rules": "routing_rules",
        "statuses": "status_rules",
        "status_rules": "status_rules",
        "delivery": "delivery_rules",
        "delivery_rules": "delivery_rules",
        "mcp": "mcp",
        "mcp_tools": "mcp_tools",
    }
)

_SECTION_RENDERERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "workflow": "Workflow:",
        "routing_rules": "Routing rules:",
        "status_rules": "Status rules:",
        "delivery_rules": "Delivery rules:",
        "recommended_mcp_tool_flow": "Recommended MCP flow:",
        "mcp_tools": "MCP tools:",
    }
)


def _normalize_view(view: str) -> str:
    normalized = str(view or "compact").strip().lower() or "compact"
    if normalized not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    return normalized


def _normalize_section(section: str | None) -> str | None:
    normalized = str(section or "").strip().lower()
    if not normalized:
        return None
    resolved = _SECTION_ALIASES.get(normalized)
    if resolved is None:
        raise ValueError(
            "section must be one of overview, workflow, routing, statuses, delivery, mcp, mcp_tools"
        )
    return resolved


def _render_text(payload: dict[str, Any]) -> str:
    lines = ["OrchestraThreads guide", str(payload.get("summary") or "")]
    for key, label in _SECTION_RENDERERS.items():
        items = payload.get(key)
        if items:
            lines.append(label)
            lines.extend(f"- {item}" for item in items)
    return "\n".join(line for line in lines if line)


def _apply_all_sections(payload: dict[str, Any], view: str) -> None:
    if view == "compact":
        payload["workflow"] = list(_FULL_GUIDE["workflow"][:5])
        payload["routing_rules"] = list(_FULL_GUIDE["routing_rules"][:3])
        payload["status_rules"] = list(_FULL_GUIDE["status_rules"][:3])
        payload["recommended_mcp_tool_flow"] = list(_FULL_GUIDE["recommended_mcp_tool_flow"])
    else:
        for key, value in _FULL_GUIDE.items():
            if key not in payload:
                payload[key] = value


_SIMPLE_SECTIONS: Final[frozenset[str]] = frozenset(
    (
        "workflow",
        "routing_rules",
        "status_rules",
        "delivery_rules",
        "mcp_tools",
    )
)


def _apply_single_section(payload: dict[str, Any], section: str, view: str) -> None:
    if section == "overview":
        limit = 4 if view == "compact" else len(_FULL_GUIDE["workflow"])
        payload["workflow"] = list(_FULL_GUIDE["workflow"][:limit])
    elif section in _SIMPLE_SECTIONS:
        payload[section] = list(_FULL_GUIDE[section])
    elif section == "mcp":
        payload["recommended_mcp_tool_flow"] = list(_FULL_GUIDE["recommended_mcp_tool_flow"])
        if view == "full":
            payload["mcp_tools"] = list(_FULL_GUIDE["mcp_tools"])


def build_instruction_payload(
    *,
    view: str = "compact",
    section: str | None = None,
) -> dict[str, Any]:
    """Build the instruction payload for the requested view and section."""
    norm_view = _normalize_view(view)
    norm_section = _normalize_section(section)
    payload_section = "all"
    if norm_section is not None:
        payload_section = str(section or "").strip().lower()
    payload: dict[str, Any] = {
        "instruction_id": GUIDE_ID,
        "service": "orchestra_threads",
        "version": GUIDE_VERSION,
        "view": norm_view,
        "section": payload_section,
        "summary": _FULL_GUIDE["summary"],
    }
    if norm_section is None:
        _apply_all_sections(payload, norm_view)
    else:
        _apply_single_section(payload, norm_section, norm_view)
    payload["text"] = _render_text(payload)
    return payload
