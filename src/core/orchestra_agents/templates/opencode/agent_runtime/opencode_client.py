from __future__ import annotations

from typing import Any

import aiohttp

_REQUEST_TIMEOUT_SECONDS = 60.0


class OpencodeClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def create_session(self) -> dict[str, Any]:
        payload = await self._json("POST", "/session")
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected create_session response payload")
        return payload

    async def send_message(self, session_id: str, text: str, *, timeout: float) -> dict[str, Any]:
        body: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        response = await self._json(
            "POST",
            f"/session/{session_id}/message",
            json_payload=body,
            timeout=timeout,
        )
        if not isinstance(response, dict):
            raise RuntimeError("unexpected send_message response payload")
        return response

    async def delete_session(self, session_id: str) -> bool:
        payload = await self._json("DELETE", f"/session/{session_id}")
        if isinstance(payload, bool):
            return payload
        if isinstance(payload, dict):
            flag = payload.get("success")
            if isinstance(flag, bool):
                return flag
        raise RuntimeError("unexpected delete_session response payload")

    async def list_sessions(self) -> list[dict[str, Any]]:
        payload = await self._json("GET", "/session")
        if not isinstance(payload, list):
            raise RuntimeError("unexpected list_sessions response payload")
        return [item for item in payload if isinstance(item, dict)]

    async def get_mcp_status(self) -> dict[str, Any]:
        payload = await self._json("GET", "/mcp")
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected get_mcp_status response payload")
        return payload

    async def _json(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        url = f"{self._base_url}{path}"
        async with self._session.request(
            method,
            url,
            json=json_payload,
            timeout=request_timeout,
        ) as response:
            response.raise_for_status()
            return await response.json(content_type=None)


async def close_client(client: OpencodeClient) -> None:
    session = client._session
    if not session.closed:
        await session.close()
