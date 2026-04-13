from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import cast
from uuid import uuid4

import aiohttp

from core.orchestra_memory.mcp.tools_common import JSON_MAP

MCP_SERVER_COMMAND = (sys.executable, "-m", "core.orchestra_memory.mcp.server")
MCP_TIMEOUT_SECONDS = 10.0
MCP_STDERR_ENCODING = "utf-8"
MCP_STDIO_ENCODING = "utf-8"
MEMORY_SERVICE_BASE_URL = os.environ.get("ORCHESTRA_MEMORY_URL", "http://orchestra-memory:8793")
MCP_REQUEST_IDS = {
    "initialize": "1",
    "tools_list": "2",
    "tool_call": "3",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _build_server_env(agent_slug: str) -> dict[str, str]:
    env = os.environ.copy()
    src_dir = _repo_root() / "src"
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_dir) if not current_pythonpath else f"{src_dir}{os.pathsep}{current_pythonpath}"
    )
    env["ORCHESTRA_AGENT_SLUG"] = agent_slug
    env["ORCHESTRA_MEMORY_URL"] = MEMORY_SERVICE_BASE_URL
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _response_id(method: str) -> str:
    if method == "initialize":
        return MCP_REQUEST_IDS["initialize"]
    if method == "tools/list":
        return MCP_REQUEST_IDS["tools_list"]
    return MCP_REQUEST_IDS["tool_call"]


def _structured_content(payload: JSON_MAP) -> JSON_MAP:
    content = payload.get("structuredContent")
    if isinstance(content, dict):
        return cast(JSON_MAP, content)
    raise AssertionError("structuredContent payload is missing")


def _start_mcp_server(agent_slug: str) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603,S607 - test starts the real MCP server
        MCP_SERVER_COMMAND,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(_repo_root()),
        env=_build_server_env(agent_slug),
        text=True,
        encoding=MCP_STDIO_ENCODING,
        errors="replace",
        bufsize=1,
    )


def _send_mcp_request_sync(process: subprocess.Popen[str], request_dict: JSON_MAP) -> JSON_MAP:
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise AssertionError("MCP process pipes are not available")
    process.stdin.write(json.dumps(request_dict, ensure_ascii=False) + "\n")
    process.stdin.flush()
    raw_response = process.stdout.readline()
    if not raw_response:
        stderr_output = process.stderr.read().strip()
        raise AssertionError(f"MCP server closed stdout unexpectedly: {stderr_output}")
    decoded = json.loads(raw_response)
    if not isinstance(decoded, dict):
        raise AssertionError("MCP response must be a JSON object")
    return cast(JSON_MAP, decoded)


async def _send_mcp_request(process: subprocess.Popen[str], request_dict: JSON_MAP) -> JSON_MAP:
    return await asyncio.wait_for(
        asyncio.to_thread(_send_mcp_request_sync, process, request_dict),
        timeout=MCP_TIMEOUT_SECONDS,
    )


async def _call_tool(
    process: subprocess.Popen[str],
    tool_name: str,
    arguments: JSON_MAP,
) -> JSON_MAP:
    response = await _send_mcp_request(
        process,
        {
            "jsonrpc": "2.0",
            "id": _response_id("tools/call"),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )
    error = response.get("error")
    if isinstance(error, dict):
        raise AssertionError(
            f"tools/call returned error: {error.get('message', 'unknown')} "
            f"(code={error.get('code', 'N/A')})"
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise AssertionError("tools/call response is missing result")
    return cast(JSON_MAP, result)


async def _post_memory_json(path: str, payload: JSON_MAP) -> tuple[int, JSON_MAP]:
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MEMORY_SERVICE_BASE_URL}{path}", json=payload) as response:
            body = await response.json()
            if not isinstance(body, dict):
                raise AssertionError("memory service response must be a JSON object")
            return response.status, cast(JSON_MAP, body)


async def _cleanup_mcp_server(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.stdin is not None:
        process.stdin.close()
    try:
        process.terminate()
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=MCP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=MCP_TIMEOUT_SECONDS)


class SecretaryMemoryE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._processes: list[subprocess.Popen[str]] = []

    async def asyncTearDown(self) -> None:
        while self._processes:
            process = self._processes.pop()
            await _cleanup_mcp_server(process)

    async def test_secretary_mcp_server_initializes(self) -> None:
        process = _start_mcp_server("secretary")
        self._processes.append(process)

        response = await _send_mcp_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": _response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )

        self.assertEqual(response["result"]["serverInfo"]["name"], "orchestra-memory-mcp")
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")

    async def test_secretary_can_remember_and_search(self) -> None:
        process = _start_mcp_server("secretary")
        self._processes.append(process)
        await _send_mcp_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": _response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )
        token = f"secretary-memory-{uuid4().hex}"

        remember_result = await _call_tool(
            process,
            "memory_remember",
            {"text": token, "room": "knowledge", "category": "fact"},
        )
        self.assertTrue(cast(bool, remember_result["structuredContent"]["ok"]))

        search_result = await _call_tool(
            process,
            "memory_search",
            {"query": token, "room": "knowledge", "limit": 10},
        )
        structured = _structured_content(search_result)
        items = structured["items"]
        self.assertEqual(structured["count"], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], token)
        self.assertEqual(items[0]["agent_slug"], "secretary")

        http_status, http_body = await _post_memory_json(
            "/memory/search",
            {"agent_slug": "secretary", "query": token, "limit": 10},
        )
        self.assertEqual(http_status, 200)
        self.assertEqual(http_body["items"][0]["text"], token)

    async def test_secretary_discovery_tools_work(self) -> None:
        process = _start_mcp_server("secretary")
        self._processes.append(process)
        await _send_mcp_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": _response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )
        token = f"secretary-discovery-{uuid4().hex}"

        await _call_tool(
            process,
            "memory_remember",
            {"text": token, "room": "profile", "category": "fact"},
        )
        rooms_result = await _call_tool(process, "memory_list_rooms", {})
        categories_result = await _call_tool(process, "memory_list_categories", {})

        rooms = _structured_content(rooms_result)["rooms"]
        categories = _structured_content(categories_result)["categories"]
        self.assertIn("profile", rooms)
        self.assertIn("fact", categories)

        rooms_status, rooms_body = await _post_memory_json(
            "/memory/discovery/rooms",
            {"agent_slug": "secretary"},
        )
        categories_status, categories_body = await _post_memory_json(
            "/memory/discovery/categories",
            {"agent_slug": "secretary"},
        )
        self.assertEqual(rooms_status, 200)
        self.assertEqual(categories_status, 200)
        self.assertIn("profile", rooms_body["rooms"])
        self.assertIn("fact", categories_body["categories"])

    async def test_secretary_slug_scoping_isolation(self) -> None:
        secretary_process = _start_mcp_server("secretary")
        orchestra_process = _start_mcp_server("orchestra")
        self._processes.extend([secretary_process, orchestra_process])

        for process in (secretary_process, orchestra_process):
            await _send_mcp_request(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": _response_id("initialize"),
                    "method": "initialize",
                    "params": {},
                },
            )

        secretary_token = f"secretary-isolation-{uuid4().hex}"
        orchestra_token = f"orchestra-isolation-{uuid4().hex}"

        await _call_tool(
            secretary_process,
            "memory_remember",
            {"text": secretary_token, "room": "knowledge", "category": "fact"},
        )
        await _call_tool(
            orchestra_process,
            "memory_remember",
            {"text": orchestra_token, "room": "knowledge", "category": "fact"},
        )

        secretary_results = _structured_content(
            await _call_tool(
                secretary_process,
                "memory_search",
                {"query": secretary_token, "room": "knowledge", "limit": 10},
            )
        )["items"]
        orchestra_results = _structured_content(
            await _call_tool(
                orchestra_process,
                "memory_search",
                {"query": orchestra_token, "room": "knowledge", "limit": 10},
            )
        )["items"]

        self.assertEqual(len(secretary_results), 1)
        self.assertEqual(secretary_results[0]["text"], secretary_token)
        self.assertEqual(secretary_results[0]["agent_slug"], "secretary")
        self.assertEqual(len(orchestra_results), 1)
        self.assertEqual(orchestra_results[0]["text"], orchestra_token)
        self.assertEqual(orchestra_results[0]["agent_slug"], "orchestra")

    async def test_secretary_memory_persists_across_restart(self) -> None:
        process = _start_mcp_server("secretary")
        self._processes.append(process)
        await _send_mcp_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": _response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )
        token = f"secretary-persist-{uuid4().hex}"

        await _call_tool(
            process,
            "memory_remember",
            {"text": token, "room": "knowledge", "category": "fact"},
        )
        initial_status, initial_body = await _post_memory_json(
            "/memory/search",
            {"agent_slug": "secretary", "query": token, "limit": 10},
        )
        self.assertEqual(initial_status, 200)
        self.assertEqual(initial_body["items"][0]["text"], token)

        await _cleanup_mcp_server(process)
        self._processes.remove(process)

        restarted_process = _start_mcp_server("secretary")
        self._processes.append(restarted_process)
        await _send_mcp_request(
            restarted_process,
            {
                "jsonrpc": "2.0",
                "id": _response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )
        search_result = _structured_content(
            await _call_tool(
                restarted_process,
                "memory_search",
                {"query": token, "room": "knowledge", "limit": 10},
            )
        )
        self.assertEqual(search_result["count"], 1)
        self.assertEqual(search_result["items"][0]["text"], token)
        self.assertEqual(search_result["items"][0]["agent_slug"], "secretary")
