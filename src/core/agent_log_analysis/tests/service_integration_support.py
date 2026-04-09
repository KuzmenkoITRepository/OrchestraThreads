"""Support helpers for agent log analysis integration parity tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

from core.agent_log_analysis.service_runtime import AgentLogAnalysisService
from core.agent_log_analysis.tests.service_integration_fixtures import analysis_payloads


@dataclass(frozen=True)
class RuntimeViews:
    event: dict[str, object]
    query_page: dict[str, object]
    timeline_page: dict[str, object]
    correlation: dict[str, object]
    aggregation: dict[str, object]
    raw_logs: dict[str, object]


async def collect_runtime_views(
    service: AgentLogAnalysisService,
    payload: dict[str, object],
) -> RuntimeViews:
    """Collect all runtime analysis views for one sample event."""
    analysis_payloads()
    event_id = cast(str, payload["event_id"])
    event = await service.get_event(event_id)
    views = await _analysis_views(service)
    return RuntimeViews(
        event=event,
        query_page=views["query_page"],
        timeline_page=views["timeline_page"],
        correlation=views["correlation"],
        aggregation=views["aggregation"],
        raw_logs=views["raw_logs"],
    )


class RuntimeAssertions:
    """Assert parity across runtime views for one ingested event."""

    @staticmethod
    def ingest_response(body: dict[str, object], event_id: str) -> None:
        assert body["status"] == "ok"
        data = cast(dict[str, object], body["data"])
        result = cast(dict[str, object], data["result"])
        assert result["event_id"] == event_id

    @staticmethod
    def event_identity(stored_event: dict[str, object], payload: dict[str, object]) -> None:
        assert stored_event["event_id"] == payload["event_id"]
        assert stored_event["agent_slug"] == payload["agent_slug"]
        assert stored_event["correlation_id"] == payload["correlation_id"]

    @staticmethod
    def event_content(stored_event: dict[str, object]) -> None:
        assert stored_event["labels"] == {"phase": "run"}
        assert stored_event["metadata"] == {"seq": 1}
        payload = _stored_payload(stored_event)
        inference = cast(dict[str, object], payload["inference"])
        raw_logs = cast(list[dict[str, object]], payload["raw_logs"])
        assert payload["raw_payload"] == {"provider": "openai"}
        assert inference["model_name"] == "gpt-4o"
        assert raw_logs[0]["raw_message"] == "message-1"

    @staticmethod
    def query_and_timeline(
        views: RuntimeViews,
        *,
        agent_slug: str,
        event_id: str,
    ) -> None:
        assert views.query_page["agent_slug"] == agent_slug
        assert _event_ids(views.query_page) == [event_id]
        assert views.timeline_page["agent_slug"] == agent_slug
        assert _event_ids(views.timeline_page) == [event_id]

    @staticmethod
    def correlation_chain(
        views: RuntimeViews,
        *,
        correlation_id: str,
        event_id: str,
    ) -> None:
        assert views.correlation["correlation_id"] == correlation_id
        assert _event_ids(views.correlation) == [event_id]

    @staticmethod
    def aggregate(views: RuntimeViews, *, agent_slug: str) -> None:
        assert views.aggregation["agent_slug"] == agent_slug
        assert views.aggregation["metrics"] == ["count"]
        assert views.aggregation["buckets"] == [
            {
                "keys": {"status": "success"},
                "count": 1,
                "success_count": 0,
                "error_count": 0,
                "avg_latency_ms": None,
            }
        ]

    @staticmethod
    def raw_logs(views: RuntimeViews, *, agent_slug: str) -> None:
        items = _page_items(views.raw_logs)
        assert views.raw_logs["agent_slug"] == agent_slug
        assert [item["log_id"] for item in items] == [1]
        assert items[0]["raw_message"] == "message-1"
        assert items[0]["raw_payload_json"] == {"idx": 1}


async def _analysis_views(service: AgentLogAnalysisService) -> dict[str, dict[str, object]]:
    requests = analysis_payloads()
    raw_results = await asyncio.gather(
        service.query_agent_events(requests["query"]),
        service.get_agent_timeline(requests["timeline"]),
        service.get_agent_correlation_chain(requests["correlation"]),
        service.aggregate_agent_events(requests["aggregate"]),
        service.get_agent_raw_logs(requests["raw_logs"]),
    )
    results = cast(list[dict[str, object]], raw_results)
    return {
        "query_page": results[0],
        "timeline_page": results[1],
        "correlation": results[2],
        "aggregation": results[3],
        "raw_logs": results[4],
    }


def _page_items(page: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], page["items"])


def _event_ids(page: dict[str, object]) -> list[object]:
    return [item["event_id"] for item in _page_items(page)]


def _stored_payload(stored_event: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], stored_event["payload"])
