"""Canonical service guide returned by OrchestraThreads and reused by MCP."""

from __future__ import annotations

from typing import Any

GUIDE_ID = "orchestra_threads_mvp"
GUIDE_VERSION = "mvp-1"

_FULL_GUIDE: dict[str, Any] = {
    "instruction_id": GUIDE_ID,
    "service": "orchestra_threads",
    "version": GUIDE_VERSION,
    "summary": (
        "Use thread_current to inspect active work, thread_send to reply or delegate, "
        "thread_status for lifecycle updates, and thread_expand only when compact state is insufficient."
    ),
    "workflow": [
        "If there is an active invocation, call thread_current first to inspect the current thread and allowed actions.",
        "Reply to the current peer with thread_send(message) and no explicit thread_id.",
        "Inside an active thread, sending to a different target_agent_slug creates or reuses a child thread.",
        "Outside an active thread, thread_send(target_agent_slug=..., message=...) creates or reuses the root pair thread.",
        "Use thread_status for in_progress, review, done, or closed updates after checking ownership rules.",
        "Use thread_expand only when compact state is insufficient for the next decision.",
    ],
    "routing_rules": [
        "Explicit thread_id continues that exact thread.",
        "Explicit parent_thread_id creates or reuses a child thread under that parent.",
        "No thread_id and no parent_thread_id create or reuse the active root thread for the pair.",
        "In MCP auto mode, replying to the source peer stays in the current thread; sending to a different target creates or reuses a child thread.",
    ],
    "status_rules": [
        "Statuses are open, in_progress, review, done, and closed.",
        "The owner can publish in_progress, done, and closed.",
        "The peer can publish in_progress and review.",
        "done and closed are terminal. closed also triggers /stop on the peer.",
    ],
    "delivery_rules": [
        "message, in_progress, review, and inactive are delivered through /event.",
        "done and closed do not wake the peer through /event.",
        "Delivery is at-least-once with retry and backoff.",
        "Terminal parent threads cascade-close live child threads.",
    ],
    "recommended_mcp_tool_flow": [
        "Call thread_current when you need to understand the active thread.",
        "Use thread_send to reply in the current thread or delegate to another agent.",
        "Use thread_status to publish progress, review, done, or closed.",
        "Use thread_expand only for details that are not present in compact state.",
        "Use thread_guide when you need to refresh the service rules or workflow.",
    ],
    "mcp_tools": [
        "thread_current: fetch compact current-thread state from active context.",
        "thread_send: reply in the current thread or route to a root or child thread.",
        "thread_status: publish in_progress, review, done, or closed.",
        "thread_expand: inspect latest, tail, related, or full thread data on demand.",
        "thread_guide: fetch the canonical OrchestraThreads workflow and rules from the service.",
    ],
}

_SECTION_ALIASES = {
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


def _lines_for(label: str, items: list[str]) -> list[str]:
    return [label] + [f"- {item}" for item in items]


def _render_text(payload: dict[str, Any]) -> str:
    lines = [
        "OrchestraThreads guide",
        str(payload.get("summary") or ""),
    ]
    if payload.get("workflow"):
        lines.extend(_lines_for("Workflow:", list(payload["workflow"])))
    if payload.get("routing_rules"):
        lines.extend(_lines_for("Routing rules:", list(payload["routing_rules"])))
    if payload.get("status_rules"):
        lines.extend(_lines_for("Status rules:", list(payload["status_rules"])))
    if payload.get("delivery_rules"):
        lines.extend(_lines_for("Delivery rules:", list(payload["delivery_rules"])))
    if payload.get("recommended_mcp_tool_flow"):
        lines.extend(
            _lines_for("Recommended MCP flow:", list(payload["recommended_mcp_tool_flow"]))
        )
    if payload.get("mcp_tools"):
        lines.extend(_lines_for("MCP tools:", list(payload["mcp_tools"])))
    return "\n".join(line for line in lines if line)


def build_instruction_payload(
    *, view: str = "compact", section: str | None = None
) -> dict[str, Any]:
    normalized_view = _normalize_view(view)
    normalized_section = _normalize_section(section)
    payload: dict[str, Any] = {
        "instruction_id": GUIDE_ID,
        "service": "orchestra_threads",
        "version": GUIDE_VERSION,
        "view": normalized_view,
        "section": "all" if normalized_section is None else str(section or "").strip().lower(),
        "summary": _FULL_GUIDE["summary"],
    }

    if normalized_section is None:
        if normalized_view == "compact":
            payload["workflow"] = list(_FULL_GUIDE["workflow"][:5])
            payload["routing_rules"] = list(_FULL_GUIDE["routing_rules"][:3])
            payload["status_rules"] = list(_FULL_GUIDE["status_rules"][:3])
            payload["recommended_mcp_tool_flow"] = list(_FULL_GUIDE["recommended_mcp_tool_flow"])
        else:
            payload.update({key: value for key, value in _FULL_GUIDE.items() if key not in payload})
    elif normalized_section == "overview":
        limit = 4 if normalized_view == "compact" else len(_FULL_GUIDE["workflow"])
        payload["workflow"] = list(_FULL_GUIDE["workflow"][:limit])
    elif normalized_section == "workflow":
        payload["workflow"] = list(_FULL_GUIDE["workflow"])
    elif normalized_section == "routing_rules":
        payload["routing_rules"] = list(_FULL_GUIDE["routing_rules"])
    elif normalized_section == "status_rules":
        payload["status_rules"] = list(_FULL_GUIDE["status_rules"])
    elif normalized_section == "delivery_rules":
        payload["delivery_rules"] = list(_FULL_GUIDE["delivery_rules"])
    elif normalized_section == "mcp":
        payload["recommended_mcp_tool_flow"] = list(_FULL_GUIDE["recommended_mcp_tool_flow"])
        if normalized_view == "full":
            payload["mcp_tools"] = list(_FULL_GUIDE["mcp_tools"])
    elif normalized_section == "mcp_tools":
        payload["mcp_tools"] = list(_FULL_GUIDE["mcp_tools"])

    payload["text"] = _render_text(payload)
    return payload
