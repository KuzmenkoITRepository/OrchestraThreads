"""Tests for agent-log-analysis HTTP handlers."""

from __future__ import annotations

from typing import Any

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.agent_log_analysis.errors import EventNotFoundError, ValidationError
from core.agent_log_analysis.http_handlers import AgentLogAnalysisHttpHandlers


class TestHttpHandlers(AioHTTPTestCase):
    """Verify HTTP transport semantics and stable envelopes."""

    async def get_application(self) -> web.Application:
        self.runtime = _FakeRuntime()
        app = web.Application()
        handlers = AgentLogAnalysisHttpHandlers(runtime=self.runtime)
        app.router.add_get("/healthz", handlers.healthz)
        app.router.add_post("/api/v1/events/ingest", handlers.ingest_event)
        app.router.add_post("/api/v1/events/ingest-batch", handlers.ingest_batch)
        app.router.add_get("/api/v1/events/{event_id}", handlers.get_event)
        return app

    async def test_healthz_ok(self) -> None:
        response = await self.client.request("GET", "/healthz")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"status": "ok"})

    async def test_ingest_success_envelope(self) -> None:
        response = await self.client.post(
            "/api/v1/events/ingest",
            json={"event_id": "evt-1"},
        )
        body = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["result"]["event_id"], "evt-1")

    async def test_ingest_duplicate_marker(self) -> None:
        self.runtime.single_response = {
            "result": {
                "event_id": "evt-1",
                "status": "ok",
                "duplicate": True,
                "error_code": None,
                "error_message": None,
            }
        }
        response = await self.client.post(
            "/api/v1/events/ingest",
            json={"event_id": "evt-1"},
        )
        body = await response.json()
        self.assertTrue(body["data"]["result"]["duplicate"])

    async def test_batch_partial_success_order(self) -> None:
        self.runtime.batch_response = {
            "items": [
                {
                    "event_id": "evt-1",
                    "status": "ok",
                    "duplicate": False,
                    "error_code": None,
                    "error_message": None,
                },
                {
                    "event_id": "batch-index-1",
                    "status": "error",
                    "duplicate": False,
                    "error_code": "VALIDATION_ERROR",
                    "error_message": "bad payload",
                },
            ]
        }
        response = await self.client.post(
            "/api/v1/events/ingest-batch",
            json={"events": [{}, {}]},
        )
        body = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(body["data"]["items"][1]["error_code"], "VALIDATION_ERROR")

    async def test_point_lookup_success(self) -> None:
        response = await self.client.get("/api/v1/events/evt-1")
        body = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(body["data"]["event"]["event_id"], "evt-1")

    async def test_point_lookup_not_found(self) -> None:
        self.runtime.raise_not_found = True
        response = await self.client.get("/api/v1/events/missing")
        body = await response.json()
        self.assertEqual(response.status, 404)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "EVENT_NOT_FOUND")


class TestHttpHandlerErrors(AioHTTPTestCase):
    """Verify error-specific HTTP mappings."""

    async def get_application(self) -> web.Application:
        self.runtime = _FakeRuntime()
        app = web.Application()
        handlers = AgentLogAnalysisHttpHandlers(runtime=self.runtime)
        app.router.add_get("/healthz", handlers.healthz)
        app.router.add_post("/api/v1/events/ingest", handlers.ingest_event)
        app.router.add_post("/api/v1/events/ingest-batch", handlers.ingest_batch)
        app.router.add_get("/api/v1/events/{event_id}", handlers.get_event)
        return app

    async def test_auth_error_maps_to_unauthorized(self) -> None:
        self.runtime.raise_validation = ValidationError(
            "AUTH_REQUIRED", "Authorization header is required"
        )
        response = await self.client.post("/api/v1/events/ingest", json={"event_id": "evt-1"})
        body = await response.json()
        self.assertEqual(response.status, 401)
        self.assertEqual(body["error_code"], "AUTH_REQUIRED")

    async def test_validation_error_maps_to_bad_request(self) -> None:
        self.runtime.raise_validation = ValidationError("VALIDATION_ERROR", "bad payload")
        response = await self.client.post("/api/v1/events/ingest", json={"event_id": "evt-1"})
        body = await response.json()
        self.assertEqual(response.status, 400)
        self.assertEqual(body["error_code"], "VALIDATION_ERROR")


class _FakeRuntime:
    def __init__(self) -> None:
        self.single_response: dict[str, Any] = {
            "result": {
                "event_id": "evt-1",
                "status": "ok",
                "duplicate": False,
                "error_code": None,
                "error_message": None,
            }
        }
        self.batch_response: dict[str, Any] = {"items": []}
        self.event_response: dict[str, Any] = {
            "event": {
                "event_id": "evt-1",
                "event_type": "inference_event",
                "occurred_at": "2025-01-01T00:00:00Z",
                "received_at": "2025-01-01T00:00:01Z",
                "agent_slug": "agent-a",
                "run_id": None,
                "thread_id": None,
                "correlation_id": None,
                "parent_event_id": None,
                "status": "success",
                "labels": {},
                "metadata": {},
                "payload": {},
                "raw_payload_attached": False,
            }
        }
        self.raise_validation: ValidationError | None = None
        self.raise_not_found = False

    async def is_healthy(self) -> bool:
        return True

    async def ingest_event(self, payload: object, *, authorization: str | None) -> dict[str, Any]:
        if payload is None and authorization == "__never__":
            return self.single_response
        if self.raise_validation is not None:
            raise self.raise_validation
        return self.single_response

    async def ingest_batch(self, payload: object, *, authorization: str | None) -> dict[str, Any]:
        if payload is None and authorization == "__never__":
            return self.batch_response
        if self.raise_validation is not None:
            raise self.raise_validation
        return self.batch_response

    async def get_event(self, event_id: str) -> dict[str, Any]:
        if self.raise_not_found:
            raise EventNotFoundError(event_id)
        return self.event_response
