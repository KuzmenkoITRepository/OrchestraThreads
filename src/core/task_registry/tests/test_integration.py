from __future__ import annotations

import asyncio
import json
import os
import unittest
import uuid
from typing import Any, cast

from core.task_registry.mcp_tools import TaskRegistryTools
from core.task_registry.store import TaskStore

JsonDict = dict[str, Any]
CREATED_BY = "integration-suite"
STATUS_DRAFT = "draft"
ASSIGNEE_ASSISTANT = "assistant"
PRIORITY_NORMAL = "normal"
KEY_TASK_ID = "task_id"
KEY_ID = "".join(("i", "d"))
KEY_OK = "ok"
KEY_STATUS = "status"
KEY_URL = "url"
KEY_TYPE = "type"
KEY_LABEL = "label"
KEY_CHECKED = "checked"
TYPE_FILE = "file"


def _default_database_url() -> str:
    return os.getenv(
        "TASK_REGISTRY_DATABASE_URL",
        "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
    )


def _parse_content(tool_result: JsonDict) -> JsonDict:
    content_parts = tool_result.get("content")
    assert isinstance(content_parts, list)
    assert content_parts
    first = content_parts[0]
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


def _by_task_id(task_id: str) -> JsonDict:
    return {KEY_TASK_ID: task_id}


def _build_title(prefix: str) -> str:
    unique_suffix = uuid.uuid4().hex
    return f"integration-{prefix}-{unique_suffix}"


class TestTaskRegistryIntegration(unittest.TestCase):  # noqa: WPS214 - integration suite keeps end-to-end MCP scenarios together
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

    def test_task_create(self) -> None:
        title = _build_title("create")
        payload = self._run(
            self._create_task(
                title=title,
                description="Create tool test",
                created_by=CREATED_BY,
                status=STATUS_DRAFT,
                assignee=ASSIGNEE_ASSISTANT,
                priority=PRIORITY_NORMAL,
                acceptance_criteria="task is created",
                checklist=[{KEY_LABEL: "first item", KEY_CHECKED: False}],
            ),
        )
        self.assertEqual(payload["title"], title)
        self.assertEqual(payload["created_by"], CREATED_BY)

    def test_task_create_with_artifacts(self) -> None:
        payload = self._run(
            self._create_task(
                title=_build_title("create-artifacts"),
                description="Create tool artifact test",
                created_by=CREATED_BY,
                artifacts=[
                    {
                        KEY_URL: "file:///tmp/create-output.txt",
                        KEY_TYPE: TYPE_FILE,
                        KEY_LABEL: "create-output",
                    },
                ],
            ),
        )
        artifact = _artifact_from_payload(payload)
        self.assertEqual(artifact[KEY_URL], "file:///tmp/create-output.txt")
        self.assertEqual(artifact[KEY_TYPE], TYPE_FILE)

    def test_task_get(self) -> None:
        created = self._run(self._create_sample_task("get"))
        task_id = created[KEY_ID]
        payload = self._get_task(task_id)
        self.assertEqual(payload[KEY_ID], task_id)
        self.assertEqual(payload["title"], created["title"])

    def test_task_list(self) -> None:
        first = self._run(self._create_sample_task("list-a"))
        second = self._run(
            self._create_task(
                title=_build_title("list-b"),
                description="Second list task",
                created_by=CREATED_BY,
                status="in_review",
                assignee="reviewer",
                priority=PRIORITY_NORMAL,
                acceptance_criteria="listed by filter",
            ),
        )
        payload = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_list",
                    {
                        KEY_STATUS: STATUS_DRAFT,
                        "assignee": ASSIGNEE_ASSISTANT,
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
        task_id = self._run(self._create_and_get_id("status"))
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_update_status",
                    {KEY_TASK_ID: task_id, KEY_STATUS: "done"},
                )
            )
        )
        self.assertTrue(ok[KEY_OK])
        self.assertEqual(self._get_task(task_id)[KEY_STATUS], "done")

    def test_task_assign(self) -> None:
        task_id = self._run(self._create_and_get_id("assign"))
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_assign",
                    {KEY_TASK_ID: task_id, "assignee": "lead-agent"},
                )
            )
        )
        self.assertTrue(ok[KEY_OK])
        self.assertEqual(self._get_task(task_id)["assignee"], "lead-agent")

    def test_task_add_comment(self) -> None:
        created = self._run(self._create_sample_task("comment"))
        task_id = created[KEY_ID]
        comment = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_add_comment",
                    {
                        KEY_TASK_ID: task_id,
                        "author": "review-bot",
                        "body": "Looks good.",
                        "artifacts": [{KEY_URL: "file:///tmp/log.txt", KEY_TYPE: TYPE_FILE}],
                    },
                ),
            ),
        )
        self.assertEqual(comment[KEY_TASK_ID], task_id)
        pool = self.store.pool
        assert pool is not None

        async def fetch_comments() -> list[JsonDict]:  # noqa: WPS430 - nested helper keeps the DB assertion local to this test
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
        task_id = created[KEY_ID]
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_add_artifact",
                    {
                        KEY_TASK_ID: task_id,
                        "artifact": {
                            KEY_URL: "file:///tmp/output.txt",
                            KEY_TYPE: TYPE_FILE,
                            KEY_LABEL: "output",
                        },
                    },
                ),
            ),
        )
        self.assertTrue(ok[KEY_OK])
        artifact = _artifact_from_payload(self._get_task(task_id))
        self.assertEqual(artifact[KEY_URL], "file:///tmp/output.txt")

    def test_task_link_thread(self) -> None:
        created = self._run(self._create_sample_task("thread"))
        task_id = created[KEY_ID]
        thread_id = str(uuid.uuid4())
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_link_thread", {KEY_TASK_ID: task_id, "thread_id": thread_id}
                )
            )
        )
        self.assertTrue(ok[KEY_OK])
        self.assertEqual(self._get_task(task_id)["linked_thread_id"], thread_id)

    def test_task_get_serializes_uuid_fields(self) -> None:
        created = self._run(self._create_sample_task("uuid"))
        task_id = created[KEY_ID]
        thread_id = str(uuid.uuid4())
        self._run(
            self.tools.dispatch("task_link_thread", {KEY_TASK_ID: task_id, "thread_id": thread_id})
        )
        payload = self._get_task(task_id)
        self.assertEqual(str(uuid.UUID(payload[KEY_ID])), task_id)
        self.assertEqual(payload["linked_thread_id"], thread_id)

    def test_task_get_checklist(self) -> None:
        created = self._run(
            self._create_task(
                title=_build_title("checklist"),
                description="Checklist test",
                created_by=CREATED_BY,
                status=STATUS_DRAFT,
                assignee=ASSIGNEE_ASSISTANT,
                priority=PRIORITY_NORMAL,
                acceptance_criteria="checklist created",
                checklist=[
                    {KEY_LABEL: "first item", KEY_CHECKED: False},
                    {KEY_LABEL: "second item", KEY_CHECKED: True},
                ],
            ),
        )
        task_id = created[KEY_ID]
        payload = self._get_checklist(task_id)
        checklist_items = cast(list[JsonDict], payload["items"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(checklist_items[0][KEY_LABEL], "first item")
        self.assertTrue(checklist_items[1][KEY_CHECKED])

    def test_task_update_checklist(self) -> None:  # noqa: WPS210 - checklist scenario needs explicit before/after payload setup
        created = self._run(
            self._create_task(
                title=_build_title("update-checklist"),
                description="Checklist update test",
                created_by=CREATED_BY,
                status=STATUS_DRAFT,
                assignee=ASSIGNEE_ASSISTANT,
                priority=PRIORITY_NORMAL,
                acceptance_criteria="checklist updated",
                checklist=[{KEY_LABEL: "toggle me", KEY_CHECKED: False}],
            ),
        )
        task_id = created[KEY_ID]
        checklist = self._get_checklist(task_id)
        checklist_items = cast(list[JsonDict], checklist["items"])
        item_id = str(checklist_items[0][KEY_ID])
        ok = _parse_content(
            self._run(
                self.tools.dispatch(
                    "task_update_checklist",
                    {"item_id": item_id, "checked": True, "checked_by": "review-bot"},
                )
            )
        )
        self.assertTrue(ok[KEY_OK])
        refreshed = self._get_checklist(task_id)
        refreshed_items = cast(list[JsonDict], refreshed["items"])
        self.assertTrue(refreshed_items[0]["checked"])
        self.assertEqual(refreshed_items[0]["checked_by"], "review-bot")

    # --- private helpers (after public tests per WPS338) ---

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

    async def _create_task(self, **arguments: Any) -> JsonDict:  # noqa: WPS210 - test helper mirrors task_create MCP payload fields
        dispatch_result = await self.tools.dispatch("task_create", arguments)
        payload = _parse_content(dispatch_result)
        payload_id = payload.get(KEY_ID)
        payload_task_id = payload.get(KEY_TASK_ID)
        task_id = str(payload_id or payload_task_id or "")
        self.assertTrue(task_id)
        self._created_task_ids.append(task_id)
        return payload

    async def _create_sample_task(self, suffix: str = "") -> JsonDict:  # noqa: WPS210 - sample fixture helper keeps payload defaults explicit in one place
        return await self._create_task(
            title=_build_title(suffix),
            description="Integration test task",
            created_by=CREATED_BY,
            status=STATUS_DRAFT,
            assignee=ASSIGNEE_ASSISTANT,
            priority="high",
            acceptance_criteria="created successfully",
        )

    def _get_task(self, task_id: str) -> JsonDict:
        raw = self._run(self.tools.dispatch("task_get", _by_task_id(task_id)))
        return _parse_content(raw)

    def _get_checklist(self, task_id: str) -> JsonDict:
        raw = self._run(self.tools.dispatch("task_get_checklist", _by_task_id(task_id)))
        return _parse_content(raw)

    async def _create_and_get_id(self, suffix: str = "") -> str:
        payload = await self._create_sample_task(suffix)
        return str(payload[KEY_ID])
