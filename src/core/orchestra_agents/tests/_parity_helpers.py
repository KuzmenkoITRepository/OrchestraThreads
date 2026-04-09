"""Shared helpers for backend semantic parity tests."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import cast

from aiohttp import ClientSession, ClientTimeout

from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    EventDelivery,
    EventDeliveryResult,
    StandardAgentApplication,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def evt_payload(delivery_id: str) -> dict[str, object]:
    """Build a minimal event delivery payload."""
    return {
        "delivery_id": delivery_id,
        "events": [
            {
                "event_id": "evt-1",
                "thread_id": "t-1",
                "event_kind": "message",
                "from_agent_slug": "secretary",
                "to_agent_slug": "parity_agent",
                "message_text": "Hello",
            }
        ],
    }


@dataclass
class BootedApp:
    """Running backend app with client session."""

    app: StandardAgentApplication
    session: ClientSession
    port: int

    async def close(self) -> None:
        """Close session and stop app."""
        await self.session.close()
        await self.app.stop()

    async def get(self, path: str) -> dict[str, object]:
        """HTTP GET."""
        return await _http_req(self.session, self.port, "GET", path)

    async def post(
        self,
        path: str,
        body: dict[str, object],
    ) -> dict[str, object]:
        """HTTP POST."""
        return await _http_req(self.session, self.port, "POST", path, body)


class _DedupBackend(BaseAgentBackend):
    """Backend with duplicate delivery detection per the semantics doc."""

    def __init__(self, *, backend_type: str) -> None:
        super().__init__(
            agent_slug="parity_agent",
            backend_type=backend_type,
            working_dir="/workspace",
        )
        self._seen: set[str] = set()

    async def handle_events(
        self,
        delivery: EventDelivery,
    ) -> EventDeliveryResult:
        """Accept delivery; duplicates return accepted=False."""
        did = delivery.delivery_id or ""
        if did in self._seen:
            return EventDeliveryResult(
                accepted=False,
                accepted_events=0,
                delivery_id=did,
                duplicate=True,
            )
        self._seen.add(did)
        self.remember_delivery(delivery)
        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=did,
        )


async def _http_req(
    session: ClientSession,
    port: int,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    url = f"http://127.0.0.1:{port}{path}"
    async with session.request(method, url, json=body) as resp:
        raw = await resp.text()
        parsed = json.loads(raw) if raw else {}
        if resp.status >= 400:
            raise AssertionError(f"{method} {path} -> {resp.status}")
        return cast(dict[str, object], parsed)


async def boot(btype: str) -> BootedApp:
    """Start a backend app on a free port."""
    backend = _DedupBackend(backend_type=btype)
    port = _free_port()
    app = StandardAgentApplication(backend=backend, host="127.0.0.1", port=port)
    await app.start()
    session = ClientSession(timeout=ClientTimeout(total=10))
    return BootedApp(app=app, session=session, port=port)
