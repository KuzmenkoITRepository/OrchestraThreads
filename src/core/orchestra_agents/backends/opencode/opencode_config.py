from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.orchestra_agents.backends.opencode.config_mcp import build_mcp_block
from core.orchestra_agents.backends.opencode.config_model import (
    build_root_payload,
    resolve_model,
)


def write_opencode_config(
    config_dir: Path,
    backend_config: dict[str, Any],
    agent_slug: str,
    working_dir: str,
) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    model = resolve_model(backend_config)
    payload = build_root_payload(model, backend_config)
    mcp_block = build_mcp_block(config_dir, backend_config, agent_slug, working_dir)
    if mcp_block:
        payload["mcp"] = mcp_block
    config_path = config_dir / "opencode.json"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    config_path.write_text(serialized, encoding="utf-8")
    return config_path
