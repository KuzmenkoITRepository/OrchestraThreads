from __future__ import annotations

from core.orchestra_agents.backends.sgr.chat_history import SessionChatHistory
from core.orchestra_agents.backends.sgr.llm_client import SGRLLMClient
from core.orchestra_agents.backends.sgr.status_tracking import SGRBackendStatus
from core.orchestra_agents.backends.sgr.tool_definitions import build_sgr_openai_tools


def build_llm_client(
    *,
    agent_slug: str,
    route_policy: str,
    timeout_seconds: float | None,
) -> SGRLLMClient:
    return SGRLLMClient(
        agent_slug=agent_slug,
        route_policy=route_policy,
        timeout_seconds=timeout_seconds,
    )


def build_openai_tools() -> list[dict[str, object]]:
    return build_sgr_openai_tools({})


def build_status() -> SGRBackendStatus:
    return SGRBackendStatus()


def build_chat_history(persist_dir: str) -> SessionChatHistory:
    return SessionChatHistory(persist_dir=persist_dir)
