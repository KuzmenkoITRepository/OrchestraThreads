from __future__ import annotations

from typing import Any


def _fake_agent_mux_script() -> str:
    import textwrap

    return textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import os
        import sys
        import time
        from pathlib import Path

        payload = json.load(sys.stdin)
        sleep_seconds = float(os.getenv("FAKE_AGENT_MUX_SLEEP", "0") or "0")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        active_context_path = os.getenv("AGENT_MUX_ACTIVE_CONTEXT_PATH")
        active_context = {}
        if active_context_path and Path(active_context_path).exists():
            active_context = json.loads(Path(active_context_path).read_text(encoding="utf-8"))

        capture = {
            "stdin_payload": payload,
            "cwd": os.getcwd(),
            "home": os.getenv("HOME"),
            "llm_proxy_api_key": os.getenv("LLM_PROXY_API_KEY"),
            "context_id_env": os.getenv("ORCHESTRA_CONTEXT_ID"),
            "event_id_env": os.getenv("AGENT_MUX_EVENT_ID"),
            "event_kind_env": os.getenv("AGENT_MUX_EVENT_KIND"),
            "dispatch_id_env": os.getenv("AGENT_MUX_DISPATCH_ID"),
            "active_context_path_env": active_context_path,
            "compat_active_context_path_env": os.getenv("ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH"),
            "codex_config": Path(os.getenv("HOME", "."), ".codex", "config.toml").read_text(encoding="utf-8"),
            "active_context": active_context,
        }
        capture_path = os.getenv("FAKE_AGENT_MUX_CAPTURE_PATH")
        if capture_path:
            Path(capture_path).write_text(json.dumps(capture, indent=2), encoding="utf-8")

        mode = os.getenv("FAKE_AGENT_MUX_MODE", "tool_call")
        if mode == "fail":
            print("simulated failure", file=sys.stderr)
            sys.exit(2)

        tool_calls = []
        response = "Draft ready for handoff."
        if mode == "tool_call":
            tool_calls = ["mcp_tool_call"]
            response = ""

        result = {
            "schema_version": 1,
            "status": "completed",
            "dispatch_id": payload.get("dispatch_id"),
            "response": response,
            "handoff_summary": "Short handoff",
            "artifacts": [],
            "activity": {
                "files_changed": [],
                "files_read": [],
                "commands_run": [],
                "tool_calls": tool_calls,
            },
            "metadata": {
                "engine": payload.get("engine"),
                "model": payload.get("model"),
                "session_id": "session-1",
            },
            "duration_ms": 12,
        }
        print(json.dumps(result))
        """
    )


def _load_backend_module() -> Any:
    import importlib

    importlib.invalidate_caches()
    return importlib.import_module("agent_runtime.backend")
