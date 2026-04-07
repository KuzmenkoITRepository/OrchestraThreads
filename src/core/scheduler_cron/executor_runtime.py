from __future__ import annotations

from datetime import UTC, datetime

import aiohttp

from core.scheduler_cron.executor_helpers import (  # noqa: WPS235
    DEFAULT_EVENT_KIND,
    SCHEDULER_SOURCE,
    as_dict,
    delivery_payload,
    dict_response,
    event_kind_from,
    render_json,
    required_str,
    scheduler_target,
)

DELIVER_ENDPOINT = "/deliver"


class JobExecutor:
    def __init__(self, events_engine_url: str, timeout_seconds: float = 30.0) -> None:
        self._events_engine_url = events_engine_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def execute(
        self, action_type: str, action_payload: dict[str, object]
    ) -> dict[str, object]:
        if self._session is None:
            raise RuntimeError("JobExecutor not started")
        started_at = datetime.now(UTC)
        result = await _execute_action(
            self._session, self._events_engine_url, action_type, action_payload
        )
        duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        return {"status": "success", "result": result, "duration_ms": duration_ms}


async def _execute_action(
    session: aiohttp.ClientSession,
    base_url: str,
    action_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    if action_type == "agent_event":
        return await _execute_agent_event(session, base_url, payload)
    if action_type == "scheduler_wakeup":
        return await _execute_scheduler_wakeup(session, base_url, payload)
    raise ValueError(f"Unknown action_type: {action_type}")


async def _execute_agent_event(
    session: aiohttp.ClientSession,
    base_url: str,
    payload: dict[str, object],
) -> dict[str, object]:
    target = required_str(payload.get("target_agent"), field="target_agent")
    event_data = as_dict(payload.get("event_data"))
    spec = _DeliverySpec(
        agent_slug=target,
        event_kind=event_kind_from(event_data),
        message_text=render_json(event_data),
        requires_response=bool(event_data.get("requires_response")),
    )
    return await _deliver(session=session, base_url=base_url, delivery=spec)


async def _execute_scheduler_wakeup(
    session: aiohttp.ClientSession,
    base_url: str,
    payload: dict[str, object],
) -> dict[str, object]:
    task = required_str(payload.get("task"), field="task")
    content: dict[str, object] = {
        "task": task,
        "context": as_dict(payload.get("context")),
        "source": SCHEDULER_SOURCE,
    }
    spec = _DeliverySpec(
        agent_slug=scheduler_target(payload.get("target_agent")),
        event_kind=DEFAULT_EVENT_KIND,
        message_text=render_json(content),
        requires_response=False,
    )
    return await _deliver(session=session, base_url=base_url, delivery=spec)


class _DeliverySpec:
    __slots__ = ("agent_slug", "event_kind", "message_text", "requires_response")

    def __init__(
        self,
        agent_slug: str,
        event_kind: str,
        message_text: str,
        requires_response: bool,
    ) -> None:
        self.agent_slug = agent_slug
        self.event_kind = event_kind
        self.message_text = message_text
        self.requires_response = requires_response


async def _deliver(
    *,
    session: aiohttp.ClientSession,
    base_url: str,
    delivery: _DeliverySpec,
) -> dict[str, object]:
    payload = delivery_payload(
        agent_slug=delivery.agent_slug,
        event_kind=delivery.event_kind,
        message_text=delivery.message_text,
        requires_response=delivery.requires_response,
    )
    response = await _post_json(session, f"{base_url}{DELIVER_ENDPOINT}", payload)
    return dict_response(response)


async def _post_json(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict[str, object],
) -> object:
    async with session.post(url, json=payload) as response:
        response.raise_for_status()
        return await response.json()
