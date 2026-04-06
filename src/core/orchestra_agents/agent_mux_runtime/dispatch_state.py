from __future__ import annotations

from typing import Any

from core.orchestra_agents.agent_mux_runtime.json_store import read_json_object, write_json_object
from core.orchestra_agents.agent_mux_runtime.state_paths import RuntimeStatePaths, utc_now


class ActiveDispatchStore:
    def __init__(self, paths: RuntimeStatePaths) -> None:
        self._paths = paths

    def remember_active_dispatch(
        self,
        *,
        dispatch_id: str,
        event_id: str | None,
        event_kind: str | None,
        artifact_dir: str | None = None,
        queue_id: str | None = None,
    ) -> None:
        active = read_json_object(self._paths.active_file)
        active[str(dispatch_id).strip()] = {
            "event_id": str(event_id or "").strip() or None,
            "event_kind": str(event_kind or "").strip() or None,
            "artifact_dir": str(artifact_dir or "").strip() or None,
            "queue_id": str(queue_id or "").strip() or None,
            "updated_at": utc_now(),
        }
        write_json_object(self._paths.active_file, active)

    def clear_active_dispatch(self, dispatch_id: str) -> None:
        active = read_json_object(self._paths.active_file)
        active.pop(str(dispatch_id or "").strip(), None)
        write_json_object(self._paths.active_file, active)

    def reset_runtime_metadata(self) -> None:
        write_json_object(self._paths.active_file, {})

    def snapshot(self) -> dict[str, Any]:
        return read_json_object(self._paths.active_file)
