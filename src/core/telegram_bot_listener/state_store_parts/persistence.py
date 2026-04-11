from __future__ import annotations

import json
from pathlib import Path

from core.telegram_bot_listener.json_types import cast_json_dict
from core.telegram_bot_listener.models import ListenerState


class PersistenceStateOps:
    def load_state(self, state_file: Path) -> ListenerState:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        return ListenerState.from_dict(cast_json_dict(payload))

    def persist_state(self, state_file: Path, state: ListenerState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(payload, encoding="utf-8")


PERSISTENCE_OPS = PersistenceStateOps()
