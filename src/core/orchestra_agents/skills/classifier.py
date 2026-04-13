"""Skill classifier for OrchestraThreads agents."""

from __future__ import annotations

from core.orchestra_agents.skills import SkillMatch
from core.orchestra_agents.skills.registry import SKILL_REGISTRY

_SEC = ("password", "token", "secret", "api_key", "credentials")

_PATS: tuple[tuple[str, tuple[str, ...], float], ...] = (
    (
        "communication",
        ("send.*message", "reply.*to", "telegram", "notify", "ответь", "напиши"),
        0.7,
    ),
    ("orchestration", ("thread", "agent", "delegate", "spawn", "status", "поток", "агент"), 0.7),
    ("memory", ("remember", "memorize", "recall", "памят", "запомни", "вспомни"), 0.7),
)


def classify_task(text: str) -> SkillMatch:
    """Classify a task into a skill using regex patterns."""
    lower = text.lower()
    if any(p in lower for p in _SEC):
        return SkillMatch("communication", 0.5, "Security-related")
    best = SkillMatch("", 0.0, None)
    for sid, pats, conf in _PATS:
        if sid not in SKILL_REGISTRY:
            continue
        n = sum(1 for p in pats if p in lower)
        if n > 0:
            c = min(1.0, conf + n * 0.1)
            if c > best.confidence:
                best = SkillMatch(sid, c, f"Matched {n} patterns")
    return best
