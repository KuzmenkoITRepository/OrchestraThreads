from __future__ import annotations

import asyncio
import json
import os
import time
import unittest
import uuid
from typing import Any

import aiohttp

from core.llm_proxy.langfuse import build_group_key


class RealBackendE2ETests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.enabled = os.getenv("E2E_REAL_BACKENDS_ENABLED") == "1"
        if not cls.enabled:
            return

        cls.llm_proxy_base_url = os.getenv("LLM_PROXY_BASE_URL", "http://localhost:8791")
        cls.langfuse_base_url = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")
        cls.langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        cls.langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")

        if not cls.langfuse_public_key or not cls.langfuse_secret_key:
            raise ValueError(
                "E2E tests enabled but LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set"
            )

    async def asyncSetUp(self) -> None:
        if not self.enabled:
            self.skipTest("E2E_REAL_BACKENDS_ENABLED not set")
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))

    async def asyncTearDown(self) -> None:
        if hasattr(self, "session"):
            await self.session.close()

    def _run_marker(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    async def _request_llm_proxy(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Make request to llm_proxy and return (status, response_data)."""
        url = f"{self.llm_proxy_base_url}{path}"
        async with self.session.request(
            method,
            url,
            json=payload,
            headers=headers,
        ) as response:
            status = response.status
            text = await response.text()
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError:
                data = {"raw": text}
            return status, data

    async def _get_langfuse_traces(
        self,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch traces from Langfuse API."""
        url = f"{self.langfuse_base_url}/api/public/traces"
        params: dict[str, Any] = {"limit": limit}
        if session_id:
            params["sessionId"] = session_id

        auth = aiohttp.BasicAuth(self.langfuse_public_key, self.langfuse_secret_key)
        async with self.session.get(url, params=params, auth=auth) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"Langfuse API error {response.status}: {text}")
            data = await response.json()
            return data.get("data", [])

    async def _wait_for_langfuse_traces(
        self,
        *,
        session_id: str,
        min_count: int = 1,
        timeout_seconds: int = 20,
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout_seconds
        last_traces: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            last_traces = await self._get_langfuse_traces(
                session_id=session_id,
                limit=max(10, min_count + 2),
            )
            if len(last_traces) >= min_count:
                return last_traces
            await asyncio.sleep(1)
        self.fail(
            f"Timed out waiting for {min_count} Langfuse trace(s) for session {session_id}. "
            f"Last seen: {len(last_traces)}"
        )

    async def _get_langfuse_trace_by_id(self, trace_id: str) -> dict[str, Any]:
        url = f"{self.langfuse_base_url}/api/public/traces/{trace_id}"
        auth = aiohttp.BasicAuth(self.langfuse_public_key, self.langfuse_secret_key)
        async with self.session.get(url, auth=auth) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"Langfuse API error {response.status}: {text}")
            data = await response.json()
            return data

    async def _get_langfuse_generations(self, trace_id: str) -> list[dict[str, Any]]:
        """Fetch generations for a trace from Langfuse API."""
        url = f"{self.langfuse_base_url}/api/public/generations"
        params = {"traceId": trace_id}
        auth = aiohttp.BasicAuth(self.langfuse_public_key, self.langfuse_secret_key)
        async with self.session.get(url, params=params, auth=auth) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"Langfuse API error {response.status}: {text}")
            data = await response.json()
            return data.get("data", [])

    def _extract_chat_completion_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        self.assertIsInstance(choices, list)
        self.assertGreater(len(choices), 0)
        first_choice = choices[0]
        self.assertIsInstance(first_choice, dict)
        message = first_choice.get("message")
        self.assertIsInstance(message, dict)
        content = message.get("content")
        self.assertIsInstance(content, str)
        self.assertTrue(content.strip())
        return content.strip()

    def _parse_json_response_text(self, text: str) -> dict[str, Any]:
        normalized = text.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            start = normalized.find("{")
            if start < 0:
                raise
            parsed, _ = json.JSONDecoder().raw_decode(normalized[start:])
        self.assertIsInstance(parsed, dict)
        return parsed

    def _serialize(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _generation_observations(self, trace_details: dict[str, Any]) -> list[dict[str, Any]]:
        observations = trace_details.get("observations", [])
        self.assertIsInstance(observations, list)
        generations = [obs for obs in observations if obs.get("type") == "GENERATION"]
        self.assertGreater(len(generations), 0, "No generations found for trace")
        return generations

    def _assert_generation_metrics(self, generation: dict[str, Any]) -> None:
        metadata = generation.get("metadata") or {}
        self.assertIn("latency_ms", metadata)
        self.assertGreater(int(metadata["latency_ms"]), 0)

        usage = generation.get("usage") or generation.get("usageDetails") or {}
        self.assertTrue(usage, "Generation missing usage metrics")
        numeric_usage_fields = {
            key: int(value) for key, value in usage.items() if isinstance(value, int | float)
        }
        self.assertTrue(numeric_usage_fields, "Generation usage has no numeric counters")
        self.assertTrue(
            all(value >= 0 for value in numeric_usage_fields.values()),
            f"Generation usage contains negative counters: {numeric_usage_fields}",
        )

        model_parameters = (
            generation.get("modelParameters") or generation.get("model_parameters") or {}
        )
        self.assertIn("temperature", model_parameters)
        self.assertEqual(float(model_parameters.get("temperature")), 0.0)

    async def test_minimax_dialogue_trace_contains_real_conversation(self) -> None:
        agent_slug = "e2e-minimax-dialogue"
        run_marker = self._run_marker("minimax-dialogue")
        context_id = f"ctx-{run_marker}"
        expected_session_id = build_group_key(agent_slug, context_id)
        self.assertIsNotNone(expected_session_id)

        headers = {
            "X-Orchestra-Agent-Slug": agent_slug,
            "X-Orchestra-Context-Id": context_id,
        }
        payload = {
            "model": "MiniMax-M2.7",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are participating in an integration test. "
                        "Reply with a compact JSON object only and no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Run marker {run_marker}. We are planning a weekend in Lisbon. "
                        "Remember the city and the pastry pastel de nata."
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        "Understood. The plan is a Lisbon weekend with tram rides and pastel de nata."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return valid JSON with keys run_marker, remembered_city, remembered_food, "
                        "final_answer. Use the exact run marker from this dialogue, remember Lisbon, "
                        "remember pastel de nata, and make final_answer one natural sentence."
                    ),
                },
            ],
        }

        status, response = await self._request_llm_proxy(
            "POST", "/minimax/v1/chat/completions", payload, headers
        )

        self.assertEqual(status, 200, f"Expected 200, got {status}: {response}")
        assistant_text = self._extract_chat_completion_text(response)
        parsed_response = self._parse_json_response_text(assistant_text)
        self.assertEqual(parsed_response.get("run_marker"), run_marker)
        self.assertEqual(parsed_response.get("remembered_city"), "Lisbon")
        self.assertIn("pastel", str(parsed_response.get("remembered_food", "")).lower())
        self.assertIn("lisbon", str(parsed_response.get("final_answer", "")).lower())

        traces = await self._wait_for_langfuse_traces(
            session_id=expected_session_id,
            min_count=1,
        )
        trace = traces[0]
        self.assertEqual(trace["sessionId"], expected_session_id)
        self.assertEqual(trace.get("name"), "llm_proxy.chat_completions")

        trace_details = await self._get_langfuse_trace_by_id(trace["id"])
        trace_input = trace_details.get("input") or {}
        self.assertEqual(trace_input.get("requested_model"), "MiniMax-M2.7")
        self.assertEqual(trace_input.get("route_policy"), "minimax_only")
        inputs_preview = trace_input.get("inputs_preview") or []
        self.assertGreaterEqual(len(inputs_preview), 3)
        roles = [item.get("role") for item in inputs_preview]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

        serialized_trace_input = self._serialize(trace_input)
        serialized_trace_details = self._serialize(trace_details)
        self.assertIn(run_marker, serialized_trace_input)
        self.assertIn("Lisbon", serialized_trace_input)
        self.assertIn("pastel de nata", serialized_trace_input)
        self.assertIn(run_marker, serialized_trace_details)

        generations = self._generation_observations(trace_details)
        generation = generations[0]
        self.assertEqual(generation.get("name"), "llm_proxy.fallback_attempt")
        self.assertEqual(generation.get("model"), "MiniMax-M2.7")
        self.assertEqual(generation.get("metadata", {}).get("selected_transport"), "fallback")
        self._assert_generation_metrics(generation)

        serialized_generation_input = self._serialize(generation.get("input"))
        serialized_generation_output = self._serialize(generation.get("output"))
        self.assertIn(run_marker, serialized_generation_input)
        self.assertTrue(generation.get("output"), "Generation output is empty")
        self.assertIn("Lisbon", serialized_generation_output)
        self.assertIn("pastel", serialized_generation_output)

    async def test_minimax_follow_up_requests_share_session_but_keep_distinct_dialogues(
        self,
    ) -> None:
        agent_slug = "e2e-minimax-session"
        run_marker = self._run_marker("minimax-session")
        context_id = f"ctx-{run_marker}"
        expected_session_id = build_group_key(agent_slug, context_id)
        self.assertIsNotNone(expected_session_id)

        headers = {
            "X-Orchestra-Agent-Slug": agent_slug,
            "X-Orchestra-Context-Id": context_id,
        }

        turn_markers = [f"{run_marker}-turn-1", f"{run_marker}-turn-2"]
        for turn_marker in turn_markers:
            payload = {
                "model": "MiniMax-M2.7",
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": "Reply with a single short line and include the requested turn marker exactly.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"This is Langfuse session test marker {turn_marker}. "
                            "Reply with: ACK <marker> Lisbon."
                        ),
                    },
                ],
            }
            status, response = await self._request_llm_proxy(
                "POST", "/minimax/v1/chat/completions", payload, headers
            )
            self.assertEqual(status, 200, f"Expected 200, got {status}: {response}")
            assistant_text = self._extract_chat_completion_text(response)
            self.assertIn(turn_marker, assistant_text)

        traces = await self._wait_for_langfuse_traces(
            session_id=expected_session_id,
            min_count=2,
        )
        self.assertGreaterEqual(len(traces), 2)

        matched_markers: set[str] = set()
        for trace in traces[:4]:
            trace_details = await self._get_langfuse_trace_by_id(trace["id"])
            generations = self._generation_observations(trace_details)
            self._assert_generation_metrics(generations[0])
            serialized_details = self._serialize(trace_details)
            for marker in turn_markers:
                if marker in serialized_details:
                    matched_markers.add(marker)
        self.assertEqual(matched_markers, set(turn_markers))

    async def test_context_rotation_creates_new_dialogue_session(self) -> None:
        agent_slug = "e2e-minimax-rotation"
        run_marker = self._run_marker("minimax-rotation")
        context_id_1 = f"ctx-{run_marker}-a"
        context_id_2 = f"ctx-{run_marker}-b"

        session_id_1 = build_group_key(agent_slug, context_id_1)
        session_id_2 = build_group_key(agent_slug, context_id_2)

        self.assertIsNotNone(session_id_1)
        self.assertIsNotNone(session_id_2)
        self.assertNotEqual(session_id_1, session_id_2)

        for context_id, marker in (
            (context_id_1, f"{run_marker}-alpha"),
            (context_id_2, f"{run_marker}-beta"),
        ):
            headers = {
                "X-Orchestra-Agent-Slug": agent_slug,
                "X-Orchestra-Context-Id": context_id,
            }
            payload = {
                "model": "MiniMax-M2.7",
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Reply with the exact marker {marker} and mention Lisbon in one sentence."
                        ),
                    }
                ],
            }
            status, response = await self._request_llm_proxy(
                "POST", "/minimax/v1/chat/completions", payload, headers
            )
            self.assertEqual(status, 200, f"Expected 200, got {status}: {response}")
            assistant_text = self._extract_chat_completion_text(response)
            self.assertIn(marker, assistant_text)

        traces_1 = await self._wait_for_langfuse_traces(session_id=session_id_1, min_count=1)
        traces_2 = await self._wait_for_langfuse_traces(session_id=session_id_2, min_count=1)

        self.assertEqual(traces_1[0]["sessionId"], session_id_1)
        self.assertEqual(traces_2[0]["sessionId"], session_id_2)

        trace_1 = await self._get_langfuse_trace_by_id(traces_1[0]["id"])
        trace_2 = await self._get_langfuse_trace_by_id(traces_2[0]["id"])
        serialized_trace_1 = self._serialize(trace_1)
        serialized_trace_2 = self._serialize(trace_2)
        self.assertIn(f"{run_marker}-alpha", serialized_trace_1)
        self.assertIn(f"{run_marker}-beta", serialized_trace_2)
        self.assertNotIn(f"{run_marker}-beta", serialized_trace_1)
        self.assertNotIn(f"{run_marker}-alpha", serialized_trace_2)


if __name__ == "__main__":
    unittest.main()
