from __future__ import annotations

from typing import Any

JsonDict = dict[str, Any]
JsonDictOrNone = JsonDict | None


def _related_threads(*, snapshot: JsonDict) -> JsonDict:
    return _RelatedThreadsBuilder(snapshot=snapshot).related_threads()


class _RelatedThreadsBuilder:
    def __init__(self, *, snapshot: JsonDict) -> None:
        self._snapshot = snapshot
        self._view = _RelatedThreadsView(snapshot=snapshot)

    def related_threads(self) -> JsonDict:
        return self._related_threads_payload(*self._related_threads_parts())

    def _related_threads_parts(self) -> tuple[list[JsonDict], JsonDict, str, str, str]:
        root_group, thread, thread_id = self._view.snapshot_parts()
        parent_thread_id, root_thread_id = self._view.relation_ids(thread)
        return (
            root_group,
            self._view.thread_payload(root_group=root_group, thread=thread, thread_id=thread_id),
            parent_thread_id,
            root_thread_id,
            thread_id,
        )

    def _related_threads_payload(
        self,
        root_group: list[JsonDict],
        thread_payload: JsonDict,
        parent_thread_id: str,
        root_thread_id: str,
        thread_id: str,
    ) -> JsonDict:
        return {
            "thread": thread_payload,
            "parent_thread": self._view.thread_by_id(
                root_group=root_group,
                thread_id=parent_thread_id,
            ),
            "root_thread": self._view.thread_by_id(
                root_group=root_group,
                thread_id=root_thread_id,
            ),
            "child_threads": self._view.child_threads(root_group=root_group, thread_id=thread_id),
        }


class _RelatedThreadsView:
    def __init__(self, *, snapshot: JsonDict) -> None:
        self._snapshot = snapshot

    def thread_payload(
        self,
        *,
        root_group: list[JsonDict],
        thread: JsonDict,
        thread_id: str,
    ) -> JsonDict:
        return next((item for item in root_group if item.get("thread_id") == thread_id), thread)

    def relation_ids(self, thread: JsonDict) -> tuple[str, str]:
        parent_thread_id = str(thread.get("parent_thread_id") or "").strip()
        root_thread_id = str(thread.get("root_thread_id") or "").strip()
        return parent_thread_id, root_thread_id

    def child_threads(self, *, root_group: list[JsonDict], thread_id: str) -> list[JsonDict]:
        return [item for item in root_group if item.get("parent_thread_id") == thread_id]

    def snapshot_parts(self) -> tuple[list[JsonDict], JsonDict, str]:
        root_group = list(self._snapshot["root_group"])
        thread = dict(self._snapshot["thread"])
        thread_id = str(self._snapshot["thread_id"])
        return root_group, thread, thread_id

    def thread_by_id(
        self,
        *,
        root_group: list[JsonDict],
        thread_id: str,
    ) -> JsonDictOrNone:
        for item in root_group:
            if item.get("thread_id") == thread_id:
                return item
        return None
