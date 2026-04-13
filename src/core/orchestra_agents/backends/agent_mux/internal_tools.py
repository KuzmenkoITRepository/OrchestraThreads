from __future__ import annotations

from typing import Any

from core.orchestra_agents.skills.registry import (
    get_skill_instructions as registry_get_skill_instructions,
)
from core.orchestra_agents.skills.registry import (
    list_skills_menu,
)


def _tool_entry(
    *,
    name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _string_prop() -> dict[str, str]:
    return {"type": "string"}


class AgentMuxInternalTools:
    list_skills = "list_skills"
    get_skill_instructions = "get_skill_instructions"
    names = frozenset((list_skills, get_skill_instructions))

    @classmethod
    def build_openai_tools(cls) -> list[dict[str, Any]]:
        return [
            _tool_entry(
                name=cls.list_skills,
                description="List all available skills with brief descriptions.",
                properties={},
                required=[],
            ),
            _tool_entry(
                name=cls.get_skill_instructions,
                description="Load detailed instructions for a specific skill.",
                properties={
                    "skill_id": _string_prop(),
                },
                required=["skill_id"],
            ),
        ]


class AgentMuxSkillToolsMixin:
    def list_skills(self) -> str:
        return list_skills(self)

    def get_skill_instructions(self, skill_id: str) -> str | None:
        return get_skill_instructions(self, skill_id)


def list_skills(_backend: object) -> str:
    return list_skills_menu()


def get_skill_instructions(_backend: object, skill_id: str) -> str | None:
    normalized_skill_id = str(skill_id or "").strip()
    if not normalized_skill_id:
        return None
    return registry_get_skill_instructions(normalized_skill_id)
