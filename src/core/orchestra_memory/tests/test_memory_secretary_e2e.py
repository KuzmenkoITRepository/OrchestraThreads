# flake8: noqa: WPS202,WPS210,WPS213,WPS217,WPS229,WPS336,WPS407,WPS476,WPS504
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
    env["PYTHONPATH"] = str(src_dir)
    if current_pythonpath:
        env["PYTHONPATH"] = os.pathsep.join((env["PYTHONPATH"], current_pythonpath))
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


async def _initialize_mcp_server(process: subprocess.Popen[str]) -> None:
    await _send_mcp_request(
        process,
        {
            "jsonrpc": "2.0",
            "id": _response_id("initialize"),
            "method": "initialize",
            "params": {},
        },
    )


async def _start_initialized_mcp_server(
    agent_slug: str,
    processes: list[subprocess.Popen[str]],
) -> subprocess.Popen[str]:
    process = _start_mcp_server(agent_slug)
    processes.append(process)
    await _initialize_mcp_server(process)
    return process


async def _remember_memory(
    process: subprocess.Popen[str],
    token: str,
    room: str,
) -> JSON_MAP:
    return await _call_tool(
        process,
        "memory_remember",
        {"text": token, "room": room, "category": "fact"},
    )


async def _search_memory_items(
    process: subprocess.Popen[str],
    query: str,
    room: str,
) -> list[JSON_MAP]:
    structured = _structured_content(
        await _call_tool(process, "memory_search", {"query": query, "room": room, "limit": 10})
    )
    return cast(list[JSON_MAP], structured["items"])


async def _check_memory_discovery(process: subprocess.Popen[str]) -> tuple[list[str], list[str]]:
    rooms_result = await _call_tool(process, "memory_list_rooms", {})
    categories_result = await _call_tool(process, "memory_list_categories", {})
    rooms = cast(list[str], _structured_content(rooms_result)["rooms"])
    categories = cast(list[str], _structured_content(categories_result)["categories"])
    return rooms, categories


async def _search_memory_http(
    query: str,
) -> tuple[int, JSON_MAP]:
    return await _post_memory_json(
        "/memory/search", {"agent_slug": "secretary", "query": query, "limit": 10}
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
        await _terminate_mcp_server(process)
    except subprocess.TimeoutExpired:
        process.kill()
        await _wait_for_mcp_server(process)


async def _terminate_mcp_server(process: subprocess.Popen[str]) -> None:
    process.terminate()
    await _wait_for_mcp_server(process)


async def _wait_for_mcp_server(process: subprocess.Popen[str]) -> None:
    await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=MCP_TIMEOUT_SECONDS)


class SecretaryMemoryE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._processes: list[subprocess.Popen[str]] = []

    async def asyncTearDown(self) -> None:
        while self._processes:
            process = self._processes.pop()
            await _cleanup_mcp_server(process)

    async def test_secretary_mcp_server_initializes(self) -> None:
        process = await _start_initialized_mcp_server("secretary", self._processes)
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
        process = await _start_initialized_mcp_server("secretary", self._processes)
        token = f"secretary-memory-{uuid4().hex}"

        remember_result = await _remember_memory(process, token, "knowledge")
        self.assertTrue(cast(bool, remember_result["structuredContent"]["ok"]))

        items = await _search_memory_items(process, token, "knowledge")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], token)
        self.assertEqual(items[0]["agent_slug"], "secretary")

        http_status, http_body = await _search_memory_http(token)
        self.assertEqual(http_status, 200)
        self.assertEqual(http_body["items"][0]["text"], token)

    async def test_secretary_discovery_tools_work(self) -> None:
        process = await _start_initialized_mcp_server("secretary", self._processes)
        token = f"secretary-discovery-{uuid4().hex}"

        await _remember_memory(process, token, "profile")
        rooms, categories = await _check_memory_discovery(process)
        self.assertIn("profile", rooms)
        self.assertIn("fact", categories)

        rooms_status, rooms_body = await _post_memory_json(
            "/memory/discovery/rooms", {"agent_slug": "secretary"}
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

        await asyncio.gather(
            _initialize_mcp_server(secretary_process),
            _initialize_mcp_server(orchestra_process),
        )

        secretary_token = f"secretary-isolation-{uuid4().hex}"
        orchestra_token = f"orchestra-isolation-{uuid4().hex}"

        await _remember_memory(secretary_process, secretary_token, "knowledge")
        await _remember_memory(orchestra_process, orchestra_token, "knowledge")

        secretary_results = await _search_memory_items(
            secretary_process, secretary_token, "knowledge"
        )
        orchestra_results = await _search_memory_items(
            orchestra_process, orchestra_token, "knowledge"
        )

        self.assertEqual(len(secretary_results), 1)
        self.assertEqual(secretary_results[0]["text"], secretary_token)
        self.assertEqual(secretary_results[0]["agent_slug"], "secretary")
        self.assertEqual(len(orchestra_results), 1)
        self.assertEqual(orchestra_results[0]["text"], orchestra_token)
        self.assertEqual(orchestra_results[0]["agent_slug"], "orchestra")

    async def test_secretary_memory_persists_across_restart(self) -> None:
        process = await _start_initialized_mcp_server("secretary", self._processes)
        token = f"secretary-persist-{uuid4().hex}"

        await _remember_memory(process, token, "knowledge")
        initial_status, initial_body = await _search_memory_http(token)
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
