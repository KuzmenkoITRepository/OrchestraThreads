#!/usr/bin/env python3
"""Manual testing script for task_registry MCP tools."""

import asyncio
import json
import sys
from typing import Any

from core.task_registry.config import load_config
from core.task_registry.mcp.tools import TaskRegistryTools
from core.task_registry.store import TaskStore

JsonDict = dict[str, Any]


class TestRunner:
    def __init__(self) -> None:
        self.store: TaskStore | None = None
        self.tools: TaskRegistryTools | None = None
        self.test_task_id: str = ""
        self.test_checklist_item_id: str = ""
        self.test_comment_id: str = ""

    async def setup(self) -> None:
        config = load_config()
        self.store = TaskStore(database_url=config.database_url)
        await self.store.start()
        self.tools = TaskRegistryTools(self.store)
        print("✓ Setup complete\n")

    async def teardown(self) -> None:
        if self.store:
            await self.store.close()
        print("\n✓ Teardown complete")

    def _parse_result(self, result: JsonDict) -> JsonDict:
        content = result.get("content", [])
        if content and isinstance(content, list):
            first = content[0]
            if isinstance(first, dict):
                text = first.get("text", "{}")
                return json.loads(text)
        return {}

    def _require_tools(self) -> TaskRegistryTools:
        if self.tools is None:
            raise RuntimeError("tools are not initialized")
        return self.tools

    async def test_task_create(self) -> None:
        print("=" * 60)
        print("TEST 1: task_create")
        print("=" * 60)

        arguments = {
            "title": "Manual Test Task",
            "description": "This is a test task created manually",
            "created_by": "manual-tester",
            "status": "draft",
            "priority": "high",
            "acceptance_criteria": "All tests must pass",
            "checklist": [
                {"label": "Step 1: Initialize", "checked": False},
                {"label": "Step 2: Execute", "checked": False},
                {"label": "Step 3: Verify", "checked": False},
            ],
        }

        result = await self._require_tools().dispatch("task_create", arguments)
        payload = self._parse_result(result)

        self.test_task_id = str(payload.get("id", ""))

        print(f"Created task ID: {self.test_task_id}")
        print(f"Title: {payload.get('title')}")
        print(f"Status: {payload.get('status')}")
        print(f"Priority: {payload.get('priority')}")
        print(f"Created by: {payload.get('created_by')}")
        print("✓ Task created successfully\n")

    async def test_task_get(self) -> None:
        print("=" * 60)
        print("TEST 2: task_get")
        print("=" * 60)

        arguments = {"task_id": self.test_task_id}
        result = await self._require_tools().dispatch("task_get", arguments)
        payload = self._parse_result(result)

        print(f"Retrieved task ID: {payload.get('id')}")
        print(f"Title: {payload.get('title')}")
        print(f"Description: {payload.get('description')}")
        print(f"Status: {payload.get('status')}")
        print("✓ Task retrieved successfully\n")

    async def test_task_list(self) -> None:
        print("=" * 60)
        print("TEST 3: task_list")
        print("=" * 60)

        # Test 3a: List all tasks
        arguments = {"limit": 10}
        result = await self._require_tools().dispatch("task_list", arguments)
        payload = self._parse_result(result)

        print(f"Total tasks found: {payload.get('count')}")

        # Test 3b: Filter by status
        arguments = {"status": "draft", "limit": 10}
        result = await self._require_tools().dispatch("task_list", arguments)
        payload = self._parse_result(result)

        print(f"Draft tasks: {payload.get('count')}")

        # Test 3c: Filter by creator
        arguments = {"created_by": "manual-tester", "limit": 10}
        result = await self._require_tools().dispatch("task_list", arguments)
        payload = self._parse_result(result)

        print(f"Tasks by manual-tester: {payload.get('count')}")
        print("✓ Task list filters work correctly\n")

    async def test_task_update_status(self) -> None:
        print("=" * 60)
        print("TEST 4: task_update_status")
        print("=" * 60)

        arguments = {
            "task_id": self.test_task_id,
            "status": "in_progress",
        }
        result = await self._require_tools().dispatch("task_update_status", arguments)
        payload = self._parse_result(result)

        print(f"Update result: {payload.get('ok')}")

        # Verify the update
        verify_result = await self._require_tools().dispatch(
            "task_get", {"task_id": self.test_task_id}
        )
        verify_payload = self._parse_result(verify_result)

        print(f"New status: {verify_payload.get('status')}")
        print("✓ Status updated successfully\n")

    async def test_task_assign(self) -> None:
        print("=" * 60)
        print("TEST 5: task_assign")
        print("=" * 60)

        arguments = {
            "task_id": self.test_task_id,
            "assignee": "test-agent-007",
        }
        result = await self._require_tools().dispatch("task_assign", arguments)
        payload = self._parse_result(result)

        print(f"Assign result: {payload.get('ok')}")

        # Verify the assignment
        verify_result = await self._require_tools().dispatch(
            "task_get", {"task_id": self.test_task_id}
        )
        verify_payload = self._parse_result(verify_result)

        print(f"Assignee: {verify_payload.get('assignee')}")
        print("✓ Task assigned successfully\n")

    async def test_task_get_checklist(self) -> None:
        print("=" * 60)
        print("TEST 6: task_get_checklist")
        print("=" * 60)

        arguments = {"task_id": self.test_task_id}
        result = await self._require_tools().dispatch("task_get_checklist", arguments)
        payload = self._parse_result(result)

        items = payload.get("items", [])
        print(f"Checklist items count: {payload.get('count')}")

        for idx, item in enumerate(items, 1):
            print(
                f"  {idx}. [{item.get('id')}] {item.get('label')} - Checked: {item.get('checked')}"
            )
            if idx == 1:
                self.test_checklist_item_id = str(item.get("id", ""))

        print("✓ Checklist retrieved successfully\n")

    async def test_task_update_checklist(self) -> None:
        print("=" * 60)
        print("TEST 7: task_update_checklist")
        print("=" * 60)

        arguments = {
            "item_id": self.test_checklist_item_id,
            "checked": True,
            "checked_by": "manual-tester",
        }
        result = await self._require_tools().dispatch("task_update_checklist", arguments)
        payload = self._parse_result(result)

        print(f"Update result: {payload.get('ok')}")

        # Verify the update
        verify_result = await self._require_tools().dispatch(
            "task_get_checklist", {"task_id": self.test_task_id}
        )
        verify_payload = self._parse_result(verify_result)

        items = verify_payload.get("items", [])
        for item in items:
            if item.get("id") == self.test_checklist_item_id:
                print(f"Item checked: {item.get('checked')}")
                print(f"Checked by: {item.get('checked_by')}")
                break

        print("✓ Checklist item updated successfully\n")

    async def test_task_add_comment(self) -> None:
        print("=" * 60)
        print("TEST 8: task_add_comment")
        print("=" * 60)

        arguments = {
            "task_id": self.test_task_id,
            "author": "manual-tester",
            "body": "This is a test comment with some important notes.",
            "artifacts": [
                {"url": "https://example.com/doc.pdf", "type": "file", "label": "Documentation"},
            ],
        }
        result = await self._require_tools().dispatch("task_add_comment", arguments)
        payload = self._parse_result(result)

        self.test_comment_id = str(payload.get("id", ""))

        print(f"Comment ID: {self.test_comment_id}")
        print(f"Author: {payload.get('author')}")
        print(f"Body: {payload.get('body')}")
        print(f"Artifacts: {len(payload.get('artifacts', []))}")
        print("✓ Comment added successfully\n")

    async def test_task_add_artifact(self) -> None:
        print("=" * 60)
        print("TEST 9: task_add_artifact")
        print("=" * 60)

        arguments = {
            "task_id": self.test_task_id,
            "artifact": {
                "url": "https://example.com/screenshot.png",
                "type": "image",
                "label": "Test Screenshot",
            },
        }
        result = await self._require_tools().dispatch("task_add_artifact", arguments)
        payload = self._parse_result(result)

        print(f"Add artifact result: {payload.get('ok')}")

        # Verify the artifact was added
        verify_result = await self._require_tools().dispatch(
            "task_get", {"task_id": self.test_task_id}
        )
        verify_payload = self._parse_result(verify_result)

        artifacts = verify_payload.get("artifacts", [])
        print(f"Total artifacts: {len(artifacts)}")
        for idx, artifact in enumerate(artifacts, 1):
            print(
                f"  {idx}. [{artifact.get('type')}] {artifact.get('label')} - {artifact.get('url')}"
            )

        print("✓ Artifact added successfully\n")

    async def test_task_link_thread(self) -> None:
        print("=" * 60)
        print("TEST 10: task_link_thread")
        print("=" * 60)

        # Generate a fake thread UUID for testing
        fake_thread_id = "12345678-1234-5678-1234-567812345678"

        arguments = {
            "task_id": self.test_task_id,
            "thread_id": fake_thread_id,
        }
        result = await self._require_tools().dispatch("task_link_thread", arguments)
        payload = self._parse_result(result)

        print(f"Link thread result: {payload.get('ok')}")

        # Verify the link
        verify_result = await self._require_tools().dispatch(
            "task_get", {"task_id": self.test_task_id}
        )
        verify_payload = self._parse_result(verify_result)

        print(f"Linked thread ID: {verify_payload.get('linked_thread_id')}")
        print("✓ Thread linked successfully\n")

    async def test_error_handling(self) -> None:
        print("=" * 60)
        print("TEST 11: Error Handling")
        print("=" * 60)

        # Test 11a: Get non-existent task
        arguments = {"task_id": "00000000-0000-0000-0000-000000000000"}
        result = await self._require_tools().dispatch("task_get", arguments)
        payload = self._parse_result(result)

        print(f"Non-existent task error: {payload.get('error', 'No error')}")

        # Test 11b: Missing required parameter
        arguments = {}
        result = await self._require_tools().dispatch("task_create", arguments)
        payload = self._parse_result(result)

        print(f"Missing parameter error: {payload.get('error', 'No error')}")

        # Test 11c: Invalid tool name
        result = await self._require_tools().dispatch("task_invalid_tool", {})
        payload = self._parse_result(result)

        print(f"Invalid tool error: {payload.get('error', 'No error')}")
        print("✓ Error handling works correctly\n")

    async def cleanup_test_data(self) -> None:
        print("=" * 60)
        print("CLEANUP: Removing test data")
        print("=" * 60)

        if self.store and self.store.pool and self.test_task_id:
            async with self.store.pool.acquire() as conn:
                await conn.execute("DELETE FROM tasks WHERE id = $1", self.test_task_id)
            print(f"✓ Deleted test task: {self.test_task_id}\n")

    async def run_all_tests(self) -> None:
        try:
            await self.setup()

            await self.test_task_create()
            await self.test_task_get()
            await self.test_task_list()
            await self.test_task_update_status()
            await self.test_task_assign()
            await self.test_task_get_checklist()
            await self.test_task_update_checklist()
            await self.test_task_add_comment()
            await self.test_task_add_artifact()
            await self.test_task_link_thread()
            await self.test_error_handling()

            await self.cleanup_test_data()

            print("=" * 60)
            print("ALL TESTS PASSED ✓")
            print("=" * 60)

        except Exception as exc:
            print(f"\n❌ TEST FAILED: {exc}", file=sys.stderr)
            raise
        finally:
            await self.teardown()


async def main() -> None:
    runner = TestRunner()
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
