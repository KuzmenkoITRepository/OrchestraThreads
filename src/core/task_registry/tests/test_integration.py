from __future__ import annotations

import asyncio
import json
import os
import unittest
import uuid
from typing import Any, cast

from core.task_registry.mcp_tools import TaskRegistryTools  # type: ignore[reportMissingImports]
from core.task_registry.store import TaskStore  # type: ignore[reportMissingImports]

JsonDict = dict[str, Any]
CREATED_BY = "integration-suite"


def _default_database_url() -> str:
    return os.getenv(
        "TASK_REGISTRY_DATABASE_URL",
        "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
    )


def _parse_content(result: JsonDict) -> JsonDict:
    content = result.get("content")
    assert isinstance(content, list)
    assert content
    first = content[0]
    assert isinstance(first, dict)
    payload = first.get("text")
    assert isinstance(payload, str)
    parsed = json.loads(payload)
    assert isinstance(parsed, dict)
    return parsed


def _artifact_from_payload(payload: JsonDict) -> JsonDict:
    artifacts = cast(list[object], payload["artifacts"])
    artifact = artifacts[-1]
    if not isinstance(artifact, dict):
        raise AssertionError(f"Expected artifact object, got: {type(artifact).__name__}")
    return cast(JsonDict, artifact)


class TestTaskRegistryIntegration(unittest.TestCase):  # noqa: WPS214
    loop: asyncio.AbstractEventLoop
    store: TaskStore
    tools: TaskRegistryTools

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.store = TaskStore(_default_database_url())
        cls.loop.run_until_complete(cls.store.start())
        cls.tools = TaskRegistryTools(cls.store)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def setUp(self) -> None:
        self._created_task_ids: list[str] = []

    def tearDown(self) -> None:
        self.loop.run_until_complete(self._cleanup_tasks())

    async def _cleanup_tasks(self) -> None:
        if not self._created_task_ids:
            return
        pool = self.store.pool
        assert pool is not None
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM tasks WHERE id = ANY($1::uuid[])",
                [str(task_id) for task_id in self._created_task_ids],
            )
        self._created_task_ids.clear()

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    async def _create_task(self, **arguments: Any) -> JsonDict:  # noqa: WPS210
        result = await self.tools.dispatch("task_create", arguments)
        payload = _parse_content(result)
        task_id = str(payload.get("id") or payload.get("task_id") or "")
        self.assertTrue(task_id)
        self._created_task_ids.append(task_id)
        return payload

    async def _create_sample_task(self, suffix: str = "") -> JsonDict:  # noqa: WPS210
        return await self._create_task(
            title=f"integration-{suffix}-{uuid.uuid4().hex}",
            description="Integration test task",
            created_by=CREATED_BY,
            status="draft",
            assignee="assistant",
            priority="high",
            acceptance_criteria="created successfully",
        )

    def test_task_create(self) -> None:
        title = f"create-{uuid.uuid4().hex}"
        payload = self._run(
            self._create_task(
                title=title,
                description="Create tool test",
                created_by=CREATED_BY,
                status="draft",
                assignee="assistant",
                priority="normal",
                acceptance_criteria="task is created",
                checklist=[{"label": "first item", "checked": False}],
            ),
        )
        self.assertEqual(payload["title"], title)
        self.assertEqual(payload["created_by"], CREATED_BY)

    def test_task_create_with_artifacts(self) -> None:
        payload = self._run(
            self._create_task(
                title=f"create-artifacts-{uuid.uuid4().hex}",
                description="Create tool artifact test",
                created_by=CREATED_BY,
                artifacts=[
                    {
                        "url": "file:///tmp/create-output.txt",
                        "type": "file",
                        "label": "create-output",
                    },
                ],
            ),
        )
        artifact = _artifact_from_payload(payload)
        self.assertEqual(artifact["url"], "file:///tmp/create-output.txt")
        self.assertEqual(artifact["type"], "file")

    def test_task_get(self) -> None:
        created = self._run(self._create_sample_task("get"))
        task_id = created["id"]
        payload = _parse_content(self._run(self.tools.dispatch("task_get", {"task_id": task_id})))
        self.assertEqual(payload["id"], task_id)
        self.assertEqual(payload["title"], created["title"])

    def test_task_list(self) -> None:
        first = self._run(self._create_sample_task("list-a"))
        second = self._run(
            self._create_task(
                title=f"integration-list-b-{uuid.uuid4().hex}",
                description="Second list task",
                created_by=CREATED_BY,
                status="in_review",
                assignee="reviewer",
                priority="normal",
                acceptance_criteria="listed by filter",
            ),
        )
        payload = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_list",
                    {
                        "status": "draft",
                        "assignee": "assistant",
                        "created_by": CREATED_BY,
                        "limit": 10,
                    },
                ),
            ),
        )
        tasks = payload["tasks"]
        self.assertIsInstance(tasks, list)
        ids = {task["id"] for task in tasks}
        self.assertIn(first["id"], ids)
        self.assertNotIn(second["id"], ids)
        self.assertEqual(payload["count"], len(tasks))

    def test_task_update_status(self) -> None:
        created = self._run(self._create_sample_task("status"))
        task_id = created["id"]
        ok = _parse_content(
            self._run(
                self.tools.dispatch("task_update_status", {"task_id": task_id, "status": "done"})
            )
        )
        self.assertTrue(ok["ok"])
        payload = _parse_content(self._run(self.tools.dispatch("task_get", {"task_id": task_id})))
        self.assertEqual(payload["status"], "done")

    def test_task_assign(self) -> None:
        created = self._run(self._create_sample_task("assign"))
        task_id = created["id"]
        ok = _parse_content(
            self._run(
                self.tools.dispatch("task_assign", {"task_id": task_id, "assignee": "lead-agent"})
            )
        )
        self.assertTrue(ok["ok"])
        payload = _parse_content(self._run(self.tools.dispatch("task_get", {"task_id": task_id})))
        self.assertEqual(payload["assignee"], "lead-agent")

    def test_task_add_comment(self) -> None:
        created = self._run(self._create_sample_task("comment"))
        task_id = created["id"]
        comment = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_add_comment",
                    {
                        "task_id": task_id,
                        "author": "review-bot",
                        "body": "Looks good.",
                        "artifacts": [{"url": "file:///tmp/log.txt", "type": "file"}],
                    },
                ),
            ),
        )
        self.assertEqual(comment["task_id"], task_id)
        pool = self.store.pool
        assert pool is not None

        async def fetch_comments() -> list[JsonDict]:  # noqa: WPS430
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM task_comments WHERE task_id = $1 ORDER BY created_at DESC",
                    task_id,
                )
            return [dict(row) for row in rows]

        comments = self._run(fetch_comments())
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["body"], "Looks good.")

    def test_task_add_artifact(self) -> None:
        created = self._run(self._create_sample_task("artifact"))
        task_id = created["id"]
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_add_artifact",
                    {
                        "task_id": task_id,
                        "artifact": {
                            "url": "file:///tmp/output.txt",
                            "type": "file",
                            "label": "output",
                        },
                    },
                ),
            ),
        )
        self.assertTrue(ok["ok"])
        payload = _parse_content(self._run(self.tools.dispatch("task_get", {"task_id": task_id})))
        artifact = _artifact_from_payload(payload)
        self.assertEqual(artifact["url"], "file:///tmp/output.txt")

    def test_task_link_thread(self) -> None:
        created = self._run(self._create_sample_task("thread"))
        task_id = created["id"]
        thread_id = str(uuid.uuid4())
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_link_thread", {"task_id": task_id, "thread_id": thread_id}
                )
            )
        )
        self.assertTrue(ok["ok"])
        payload = _parse_content(self._run(self.tools.dispatch("task_get", {"task_id": task_id})))
        self.assertEqual(payload["linked_thread_id"], thread_id)

    def test_task_get_serializes_uuid_fields(self) -> None:
        created = self._run(self._create_sample_task("uuid"))
        task_id = created["id"]
        thread_id = str(uuid.uuid4())
        self._run(
            self.tools.dispatch("task_link_thread", {"task_id": task_id, "thread_id": thread_id})
        )
        payload = _parse_content(self._run(self.tools.dispatch("task_get", {"task_id": task_id})))
        self.assertEqual(str(uuid.UUID(payload["id"])), task_id)
        self.assertEqual(payload["linked_thread_id"], thread_id)

    def test_task_get_checklist(self) -> None:
        created = self._run(
            self._create_task(
                title=f"integration-checklist-{uuid.uuid4().hex}",
                description="Checklist test",
                created_by=CREATED_BY,
                status="draft",
                assignee="assistant",
                priority="normal",
                acceptance_criteria="checklist created",
                checklist=[
                    {"label": "first item", "checked": False},
                    {"label": "second item", "checked": True},
                ],
            ),
        )
        task_id = created["id"]
        payload = _parse_content(
            self._run(self.tools.dispatch("task_get_checklist", {"task_id": task_id}))
        )
        items = cast(list[JsonDict], payload["items"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(items[0]["label"], "first item")
        self.assertTrue(items[1]["checked"])

    def test_task_update_checklist(self) -> None:  # noqa: WPS210
        created = self._run(
            self._create_task(
                title=f"integration-update-checklist-{uuid.uuid4().hex}",
                description="Checklist update test",
                created_by=CREATED_BY,
                status="draft",
                assignee="assistant",
                priority="normal",
                acceptance_criteria="checklist updated",
                checklist=[{"label": "toggle me", "checked": False}],
            ),
        )
        task_id = created["id"]
        checklist = _parse_content(
            self._run(self.tools.dispatch("task_get_checklist", {"task_id": task_id}))
        )
        items = cast(list[JsonDict], checklist["items"])
        item_id = str(items[0]["id"])
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_update_checklist",
                    {"item_id": item_id, "checked": True, "checked_by": "review-bot"},
                )
            )
        )
        self.assertTrue(ok["ok"])
        refreshed = _parse_content(
            self._run(self.tools.dispatch("task_get_checklist", {"task_id": task_id}))
        )
        refreshed_items = cast(list[JsonDict], refreshed["items"])
        self.assertTrue(refreshed_items[0]["checked"])
        self.assertEqual(refreshed_items[0]["checked_by"], "review-bot")
