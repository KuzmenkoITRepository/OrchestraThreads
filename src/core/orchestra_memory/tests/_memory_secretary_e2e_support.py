from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import aiohttp

from core.orchestra_memory.mcp.tools_common import JSON_MAP

MEMORY_SERVICE_BASE_URL = os.environ.get(
    "ORCHESTRA_MEMORY_URL",
    "http://orchestra-memory:8793",
)
SERVER_COMMAND = (sys.executable, "-m", "core.orchestra_memory.mcp.server")
MCP_TIMEOUT_SECONDS = 10.0
MCP_STDIO_ENCODING = "utf-8"


async def _wait_for_process_exit(process: subprocess.Popen[str]) -> None:
    await asyncio.wait_for(
        asyncio.to_thread(process.wait),
        timeout=MCP_TIMEOUT_SECONDS,
    )


async def _terminate_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    await _wait_for_process_exit(process)


class SecretaryServerSupport:
    @staticmethod
    def repo_root() -> Path:
        return Path(__file__).resolve().parents[4]

    @staticmethod
    def build_server_env(agent_slug: str) -> dict[str, str]:
        env = os.environ.copy()
        src_dir = SecretaryServerSupport.repo_root() / "src"
        current_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_dir)
        if current_pythonpath:
            env["PYTHONPATH"] = os.pathsep.join((env["PYTHONPATH"], current_pythonpath))
        env["ORCHESTRA_AGENT_SLUG"] = agent_slug
        env["ORCHESTRA_MEMORY_URL"] = MEMORY_SERVICE_BASE_URL
        env["PYTHONUNBUFFERED"] = "1"
        return env

    @staticmethod
    def start_mcp_server(agent_slug: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            SERVER_COMMAND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(SecretaryServerSupport.repo_root()),
            env=SecretaryServerSupport.build_server_env(agent_slug),
            text=True,
            encoding=MCP_STDIO_ENCODING,
            errors="replace",
            bufsize=1,
        )

    @staticmethod
    async def start_initialized_server(
        agent_slug: str,
        processes: list[subprocess.Popen[str]],
    ) -> subprocess.Popen[str]:
        process = SecretaryServerSupport.start_mcp_server(agent_slug)
        processes.append(process)
        await SecretaryRpcSupport.initialize_server(process)
        return process

    @staticmethod
    async def restart_server(
        process: subprocess.Popen[str],
        agent_slug: str,
        processes: list[subprocess.Popen[str]],
    ) -> subprocess.Popen[str]:
        await SecretaryServerSupport.cleanup_server(process)
        processes.remove(process)
        return await SecretaryServerSupport.start_initialized_server(agent_slug, processes)

    @staticmethod
    async def cleanup_server(process: subprocess.Popen[str] | None) -> None:
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            await _terminate_process(process)
        except subprocess.TimeoutExpired:
            process.kill()
            await _wait_for_process_exit(process)


class SecretaryRpcSupport:
    @staticmethod
    def response_id(method: str) -> str:
        if method == "initialize":
            return "1"
        if method == "tools/list":
            return "2"
        return "3"

    @staticmethod
    def send_request_sync(
        process: subprocess.Popen[str],
        request_dict: JSON_MAP,
    ) -> JSON_MAP:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise AssertionError("MCP process pipes are not available")
        process.stdin.write(f"{json.dumps(request_dict, ensure_ascii=False)}\n")
        process.stdin.flush()
        raw_response = process.stdout.readline()
        if not raw_response:
            stderr_output = process.stderr.read().strip()
            raise AssertionError(
                f"MCP server closed stdout unexpectedly: {stderr_output}",
            )
        decoded = json.loads(raw_response)
        if not isinstance(decoded, dict):
            raise AssertionError("MCP response must be a JSON object")
        return cast(JSON_MAP, decoded)

    @staticmethod
    async def send_request(
        process: subprocess.Popen[str],
        request_dict: JSON_MAP,
    ) -> JSON_MAP:
        return await asyncio.wait_for(
            asyncio.to_thread(SecretaryRpcSupport.send_request_sync, process, request_dict),
            timeout=MCP_TIMEOUT_SECONDS,
        )

    @staticmethod
    async def initialize_server(process: subprocess.Popen[str]) -> None:
        await SecretaryRpcSupport.send_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": SecretaryRpcSupport.response_id("initialize"),
                "method": "initialize",
                "params": {},
            },
        )

    @staticmethod
    def structured_content(payload: JSON_MAP) -> JSON_MAP:
        content = payload.get("structuredContent")
        if isinstance(content, dict):
            return cast(JSON_MAP, content)
        raise AssertionError("structuredContent payload is missing")

    @staticmethod
    async def call_tool(
        process: subprocess.Popen[str],
        tool_name: str,
        arguments: JSON_MAP,
    ) -> JSON_MAP:
        response = await SecretaryRpcSupport.send_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": SecretaryRpcSupport.response_id("tools/call"),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        error = response.get("error")
        if isinstance(error, dict):
            raise AssertionError(
                f"tools/call returned error: {error.get('message', 'unknown')} "
                f"(code={error.get('code', 'N/A')})",
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise AssertionError("tools/call response is missing result")
        return cast(JSON_MAP, result)


class SecretaryMemorySupport:
    @staticmethod
    async def remember_memory(
        process: subprocess.Popen[str],
        token: str,
        room: str,
    ) -> JSON_MAP:
        return await SecretaryRpcSupport.call_tool(
            process,
            "memory_remember",
            {"text": token, "room": room, "category": "fact"},
        )

    @staticmethod
    async def search_memory_result(
        process: subprocess.Popen[str],
        query: str,
        room: str,
    ) -> JSON_MAP:
        return SecretaryRpcSupport.structured_content(
            await SecretaryRpcSupport.call_tool(
                process,
                "memory_search",
                {"query": query, "room": room, "limit": 10},
            ),
        )

    @staticmethod
    async def search_memory_items(
        process: subprocess.Popen[str],
        query: str,
        room: str,
    ) -> list[JSON_MAP]:
        structured = await SecretaryMemorySupport.search_memory_result(process, query, room)
        return cast(list[JSON_MAP], structured["items"])

    @staticmethod
    async def check_memory_discovery(
        process: subprocess.Popen[str],
    ) -> tuple[list[str], list[str]]:
        rooms_result = await SecretaryRpcSupport.call_tool(
            process,
            "memory_list_rooms",
            {},
        )
        categories_result = await SecretaryRpcSupport.call_tool(
            process,
            "memory_list_categories",
            {},
        )
        rooms = cast(list[str], SecretaryRpcSupport.structured_content(rooms_result)["rooms"])
        categories = cast(
            list[str],
            SecretaryRpcSupport.structured_content(categories_result)["categories"],
        )
        return rooms, categories

    @staticmethod
    async def post_memory_json(
        path: str,
        payload: JSON_MAP,
    ) -> tuple[int, JSON_MAP]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MEMORY_SERVICE_BASE_URL}{path}",
                json=payload,
            ) as response:
                body = await response.json()
                if not isinstance(body, dict):
                    raise AssertionError(
                        "memory service response must be a JSON object",
                    )
                return response.status, cast(JSON_MAP, body)

    @staticmethod
    async def search_memory_http(
        query: str,
    ) -> tuple[int, JSON_MAP]:
        return await SecretaryMemorySupport.post_memory_json(
            "/memory/search",
            {"agent_slug": "secretary", "query": query, "limit": 10},
        )
