"""MCP tool: thread_peers — list agents available for communication."""

from __future__ import annotations

from typing import Any

from core.orchestra_thread.mcp_tools_common import result

AgentItem = dict[str, Any]
AgentItems = list[AgentItem]


async def thread_peers(server: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return list of registered agents the caller can communicate with."""
    response = await server.client.list_agents()
    agents = response.get("agents", [])
    caller = server.agent_slug
    peers = _filtered_peers(agents, caller)
    return result({"ok": True, "peers": peers, "count": len(peers)})


def _filtered_peers(agents: AgentItems, caller: str) -> AgentItems:
    peers = _build_peer_list(agents, caller)
    allowed = _allowed_peer_slugs(agents, caller)
    if not allowed:
        return peers
    return _allowed_peers(peers, allowed)


def _build_peer_list(agents: AgentItems, caller: str) -> AgentItems:
    peers: AgentItems = []
    for agent_payload in agents:
        slug = str(agent_payload.get("agent_slug", "")).strip()
        if not slug or slug == caller:
            continue
        peers.append(
            {
                "agent_slug": slug,
                "display_name": str(agent_payload.get("display_name") or slug),
                "online": bool(agent_payload.get("online")),
            }
        )
    return peers


def _allowed_peer_slugs(agents: AgentItems, caller: str) -> set[str]:
    for agent_payload in agents:
        slug = str(agent_payload.get("agent_slug", "")).strip()
        if slug != caller:
            continue
        metadata = agent_payload.get("metadata") or agent_payload.get("metadata_json") or {}
        return _normalized_allowed_slugs(metadata.get("allowed_peer_agent_slugs"))
    return set()


def _peer_slug(peer: AgentItem) -> str:
    return str(peer.get("agent_slug") or "")


def _allowed_peers(peers: AgentItems, allowed: set[str]) -> AgentItems:
    return [peer for peer in peers if _peer_slug(peer) in allowed]


def _normalized_allowed_slugs(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set()
    normalized: set[str] = set()
    for slug_item in raw:
        slug = str(slug_item).strip()
        if slug:
            normalized.add(slug)
    return normalized
