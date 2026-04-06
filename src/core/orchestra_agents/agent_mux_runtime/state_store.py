from __future__ import annotations

from pathlib import Path
from typing import Any

from core.orchestra_agents.agent_mux_runtime.context_store import RuntimeContextStore
from core.orchestra_agents.agent_mux_runtime.dispatch_state import ActiveDispatchStore
from core.orchestra_agents.agent_mux_runtime.json_store import write_json_object
from core.orchestra_agents.agent_mux_runtime.queue_store import RuntimeQueueStore
from core.orchestra_agents.agent_mux_runtime.state_paths import RuntimeStatePaths, sanitize_fragment


def _write_default_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.exists():
        write_json_object(path, payload)


class AgentMuxRuntimeState:
    def __init__(self, root_dir: str) -> None:
        self._paths = RuntimeStatePaths.from_root_dir(root_dir)
        self._queue_store = RuntimeQueueStore(self._paths)
        self._context_store = RuntimeContextStore(self._paths)
        self._dispatch_store = ActiveDispatchStore(self._paths)

    def ensure_layout(self) -> None:
        self._paths.ensure_layout()
        _write_default_json(self._paths.handled_file, {})
        _write_default_json(self._paths.active_file, {})
        _write_default_json(self._paths.counter_file, {"value": 0})
        _write_default_json(self._paths.context_file, {})

    def __getattr__(self, name: str) -> Any:
        if name == "root_dir":
            return str(self._paths.root)
        if hasattr(self._paths, name):
            return getattr(self._paths, name)
        self.ensure_layout()
        for store in (self._queue_store, self._context_store, self._dispatch_store):
            if hasattr(store, name):
                return getattr(store, name)
        message = f"{type(self).__name__!s} has no attribute {name!r}"
        raise AttributeError(message)

    def artifact_dir_for_dispatch(self, dispatch_id: str) -> Path:
        self.ensure_layout()
        return self._paths.artifacts_dir / sanitize_fragment(dispatch_id)

    def codex_home_dir(self) -> Path:
        self.ensure_layout()
        return self._paths.home_dir

    def status_snapshot(self) -> dict[str, Any]:
        self.ensure_layout()
        active = self._dispatch_store.snapshot()
        return {
            "runtime_state_root": str(self._paths.root),
            "context": self._context_store.context_snapshot(),
            "queue_size": self._queue_store.queue_size(),
            "queued_events_by_kind": self._queue_store.queued_events_by_kind(),
            "failed_queue_size": self._queue_store.failed_count(),
            "active_dispatches": active,
            "active_dispatch_count": len(active),
            "handled_event_count": self._queue_store.handled_count(),
            "active_context_path": str(self._paths.active_context_path),
        }
