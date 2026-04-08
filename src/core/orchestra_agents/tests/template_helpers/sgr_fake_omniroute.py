"""Fake OmniRoute LLM gateway for SGR backend tests."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from core.orchestra_agents.tests.template_helpers.sgr_fake_thread import _free_port

_JsonDict = dict[str, Any]
FakePayload = _JsonDict | list[_JsonDict]

_ERROR_STATUS = 500  # noqa: WPS432
_DEFAULT_MODEL = "MiniMax-M2.7"


class FakeOmniRoute:
    """In-process fake of the OmniRoute LLM gateway."""

    def __init__(self) -> None:
        self.port = _free_port()
        self.runner: web.AppRunner | None = None
        self.chat_requests: list[_JsonDict] = []
        self.responses: list[FakePayload] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def enqueue(self, payload: FakePayload) -> None:
        self.responses.append(payload)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/v1/chat/completions", self._handle_chat)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self.port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _handle_chat(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.chat_requests.append(
            {
                "path": request.path,
                "headers": dict(request.headers),
                "payload": payload,
                "request": request,
            }
        )
        if not self.responses:
            return web.json_response(
                {"error": {"message": "No queued fake LLM response"}},
                status=_ERROR_STATUS,
            )
        queued_payload = self.responses.pop(0)
        if payload.get("stream"):
            return await _stream_response(self, queued_payload)
        return _non_stream_response(queued_payload, payload)


def _non_stream_response(queued_payload: FakePayload, payload: _JsonDict) -> web.Response:
    if not isinstance(queued_payload, dict):
        return web.json_response(
            {"error": {"message": "Expected non-stream response payload"}},
            status=_ERROR_STATUS,
        )
    body = dict(queued_payload)
    body["model"] = payload.get("model") or body.get("model") or _DEFAULT_MODEL
    return web.json_response(body)


async def _stream_response(
    omniroute: FakeOmniRoute,
    response_payload: FakePayload,
) -> web.StreamResponse:
    stream = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    request = omniroute.chat_requests[-1]["request"]
    await stream.prepare(request)
    chunks = response_payload if isinstance(response_payload, list) else [response_payload]
    lines = [f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks]
    lines.append("data: [DONE]\n\n")
    await stream.write("".join(lines).encode())
    await stream.write_eof()
    return stream
