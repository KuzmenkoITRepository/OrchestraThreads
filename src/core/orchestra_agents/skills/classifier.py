"""Skill classifier for OrchestraThreads agents."""

from __future__ import annotations

from dataclasses import dataclass

from core.orchestra_agents.skills import SkillMatch
from core.orchestra_agents.skills.registry import SKILL_REGISTRY

_SEC = ("password", "token", "secret", "api_key", "credentials")


@dataclass(frozen=True, slots=True)
class PatternRule:
    """One keyword rule for skill classification."""

    skill_id: str
    patterns: tuple[str, ...]
    confidence: float


_PATS: tuple[PatternRule, ...] = (
    PatternRule(
        "communication",
        ("send.*message", "reply.*to", "telegram", "notify", "ответь", "напиши"),
        0.7,
    ),
    PatternRule(
        "orchestration", ("thread", "agent", "delegate", "spawn", "status", "поток", "агент"), 0.7
    ),
    PatternRule("memory", ("remember", "memorize", "recall", "памят", "запомни", "вспомни"), 0.7),
)


def _score_rule(lower: str, rule: PatternRule) -> SkillMatch | None:
    """Return a match when at least one pattern hits."""
    if rule.skill_id not in SKILL_REGISTRY:
        return None
    matched = sum(1 for pattern in rule.patterns if pattern in lower)
    if matched == 0:
        return None
    confidence = min(1.0, rule.confidence + matched * 0.1)
    return SkillMatch(rule.skill_id, confidence, f"Matched {matched} patterns")


def classify_task(text: str) -> SkillMatch:
    """Classify a task into a skill using regex patterns."""
    lower = text.lower()
    if any(p in lower for p in _SEC):
        return SkillMatch("communication", 0.5, "Security-related")
    best = SkillMatch("", -1.0, None)
    for rule in _PATS:
        match = _score_rule(lower, rule)
        if match is not None and match.confidence > best.confidence:
            best = match
    return best
