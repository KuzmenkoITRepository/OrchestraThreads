"""Backend-agnostic skill system for OrchestraThreads agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_SKILLS_DIR = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class Skill:
    """A skill definition with menu text and detailed instructions."""

    skill_id: str
    name: str
    description: str
    filename: str

    @property
    def menu_entry(self) -> str:
        """Menu entry for progressive disclosure."""
        return f"- **{self.skill_id}**: {self.description}"


@dataclass(slots=True)
class SkillMatch:
    """Result of skill classification."""

    skill_id: str
    confidence: float
    reason: str | None = None


class SkillClassifier(Protocol):
    """Protocol for skill classification."""

    def classify(self, text: str) -> SkillMatch: ...
