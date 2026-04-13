"""Skill registry for OrchestraThreads agents.

Skills are backend-agnostic workflow definitions that provide progressive
disclosure: a menu of skills is shown in the base prompt, and the agent
can request detailed instructions for a specific skill when needed.
"""

from __future__ import annotations

from pathlib import Path

from core.orchestra_agents.skills import Skill

_SKILLS_DIR = Path(__file__).parent


def _mk_skill(sid: str, name: str, desc: str, fname: str) -> Skill:
    return Skill(sid, name, desc, fname)


_COMM_SKILL = _mk_skill(
    "communication",
    "Communication",
    "Send messages to users via Telegram or other channels",
    "communication.md",
)

_ORCH_SKILL = _mk_skill(
    "orchestration",
    "Orchestration",
    "Manage threads, delegate to agents, track status",
    "orchestration.md",
)

_MEM_SKILL = _mk_skill(
    "memory",
    "Memory",
    "Store and retrieve persistent memory entries",
    "memory.md",
)

SKILL_REGISTRY = {
    _COMM_SKILL.skill_id: _COMM_SKILL,
    _ORCH_SKILL.skill_id: _ORCH_SKILL,
    _MEM_SKILL.skill_id: _MEM_SKILL,
}


def list_skills_menu() -> str:
    """Return a compact menu of all available skills."""
    lines = [
        "<AVAILABLE_SKILLS>",
        "Call get_skill_instructions(skill_id) to load full workflow before acting.",
    ]
    for skill in SKILL_REGISTRY.values():
        lines.append(skill.menu_entry)
    lines.append("</AVAILABLE_SKILLS>")
    return "\n".join(lines)


def get_skill_instructions(sid: str) -> str | None:
    """Load the full instructions for a skill from its .md file."""
    skill = SKILL_REGISTRY.get(sid)
    if skill is None:
        return None
    fpath = _SKILLS_DIR / skill.filename
    if not fpath.is_file():
        return None
    return fpath.read_text(encoding="utf-8").strip()
