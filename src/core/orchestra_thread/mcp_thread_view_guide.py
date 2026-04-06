from __future__ import annotations

import json
from typing import Any

from core.orchestra_thread.mcp_tools_common import JSON_MAP, normalize_optional_str, result


def _thread_guide_structured(instruction: JSON_MAP) -> JSON_MAP:
    return {
        "ok": True,
        "operation": "thread_guide",
        **{key: value for key, value in instruction.items() if key != "text"},
    }


def _thread_guide_text(instruction: JSON_MAP) -> str:
    text = str(instruction.get("text") or "").strip()
    if text:
        return text
    return json.dumps(instruction, ensure_ascii=False)


async def thread_guide(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    payload = await server.client.get_instruction(
        view=str(arguments.get("view") or "compact"),
        section=normalize_optional_str(arguments.get("section")),
    )
    instruction = payload.get("instruction") or {}
    return result(_thread_guide_structured(instruction), text=_thread_guide_text(instruction))
