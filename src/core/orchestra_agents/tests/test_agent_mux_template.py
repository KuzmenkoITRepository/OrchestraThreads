from __future__ import annotations

import importlib
import json
import os
import socket
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

from core.orchestra_agents.runtime import EventDelivery, StopRequest
from core.orchestra_agents.scaffold import scaffold_agent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _purge_agent_runtime_modules() -> None:
    for name in list(sys.modules.keys()):
        if name == "agent_runtime" or name.startswith("agent_runtime."):
            sys.modules.pop(name, None)


async def _wait_for(predicate, *, timeout: float = 5.0) -> Any:
    import asyncio
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.05)
    return None


class AgentMuxTemplateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.agent_dir = self.root / "generic_worker"
        scaffold_agent(
            slug="generic_worker",
            output_dir=self.agent_dir,
            display_name="Generic Worker",
            backend_type="agent_mux",
            template="agent_mux",
        )
        self.capture_path = self.root / "agent-mux-capture.json"
        self.agent_mux_binary = self.root / "fake-agent-mux"
        self.agent_mux_binary.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                import time
                from pathlib import Path

                payload = json.load(sys.stdin)
                sleep_seconds = float(os.getenv("FAKE_AGENT_MUX_SLEEP", "0") or "0")
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

                active_context_path = os.getenv("AGENT_MUX_ACTIVE_CONTEXT_PATH")
                active_context = {}
                if active_context_path and Path(active_context_path).exists():
                    active_context = json.loads(Path(active_context_path).read_text(encoding="utf-8"))

                capture = {
                    "stdin_payload": payload,
                    "cwd": os.getcwd(),
                    "home": os.getenv("HOME"),
                    "llm_proxy_api_key": os.getenv("LLM_PROXY_API_KEY"),
                    "context_id_env": os.getenv("ORCHESTRA_CONTEXT_ID"),
                    "event_id_env": os.getenv("AGENT_MUX_EVENT_ID"),
                    "event_kind_env": os.getenv("AGENT_MUX_EVENT_KIND"),
                    "dispatch_id_env": os.getenv("AGENT_MUX_DISPATCH_ID"),
                    "active_context_path_env": active_context_path,
                    "compat_active_context_path_env": os.getenv("ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH"),
                    "codex_config": Path(os.getenv("HOME", "."), ".codex", "config.toml").read_text(encoding="utf-8"),
                    "active_context": active_context,
                }
                capture_path = os.getenv("FAKE_AGENT_MUX_CAPTURE_PATH")
                if capture_path:
                    Path(capture_path).write_text(json.dumps(capture, indent=2), encoding="utf-8")

                mode = os.getenv("FAKE_AGENT_MUX_MODE", "tool_call")
                if mode == "fail":
                    print("simulated failure", file=sys.stderr)
                    sys.exit(2)

                tool_calls = []
                response = "Draft ready for handoff."
                if mode == "tool_call":
                    tool_calls = ["mcp_tool_call"]
                    response = ""

                result = {
                    "schema_version": 1,
                    "status": "completed",
                    "dispatch_id": payload.get("dispatch_id"),
                    "response": response,
                    "handoff_summary": "Short handoff",
                    "artifacts": [],
                    "activity": {
                        "files_changed": [],
                        "files_read": [],
                        "commands_run": [],
                        "tool_calls": tool_calls,
                    },
                    "metadata": {
                        "engine": payload.get("engine"),
                        "model": payload.get("model"),
                        "session_id": "session-1",
                    },
                    "duration_ms": 12,
                }
                print(json.dumps(result))
                """
            ),
            encoding="utf-8",
        )
        self.agent_mux_binary.chmod(self.agent_mux_binary.stat().st_mode | stat.S_IXUSR)

        self.previous_env = {
            "FAKE_AGENT_MUX_MODE": os.environ.get("FAKE_AGENT_MUX_MODE"),
            "FAKE_AGENT_MUX_SLEEP": os.environ.get("FAKE_AGENT_MUX_SLEEP"),
            "FAKE_AGENT_MUX_CAPTURE_PATH": os.environ.get("FAKE_AGENT_MUX_CAPTURE_PATH"),
            "PYTHONPATH": os.environ.get("PYTHONPATH"),
        }
        os.environ["FAKE_AGENT_MUX_CAPTURE_PATH"] = str(self.capture_path)
        os.environ["PYTHONPATH"] = f"/workspace/src:{self.agent_dir}"

        _purge_agent_runtime_modules()
        sys.path.insert(0, str(self.agent_dir))
        importlib.invalidate_caches()
        self.backend_module = importlib.import_module("agent_runtime.backend")
        self.AgentMuxBackend = self.backend_module.AgentMuxBackend

    async def asyncTearDown(self) -> None:
        _purge_agent_runtime_modules()
        try:
            sys.path.remove(str(self.agent_dir))
        except ValueError:
            pass
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def _mcp_server_config(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "orchestra_threads",
                "command": "python",
                "args": ["-m", "core.orchestra_thread.mcp_server"],
                "cwd": "{working_dir}",
                "startup_timeout_sec": 15,
                "required": False,
                "enabled": True,
                "enabled_tools": [
                    "thread_send",
                    "thread_status",
                    "thread_current",
                    "thread_expand",
                    "thread_guide",
                ],
                "env": {
                    "ORCHESTRA_THREADS_AGENT_SLUG": "{agent_slug}",
                    "ORCHESTRA_THREADS_URL": "http://127.0.0.1:8788",
                    "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH": "{active_context_path}",
                    "PYTHONPATH": "{pythonpath}",
                },
            }
        ]

    async def _start_backend(
        self,
        *,
        require_tool_call_for_response: bool = False,
        include_mcp_server: bool = False,
        max_attempts: int = 2,
    ):
        backend = self.AgentMuxBackend(
            agent_slug="generic_worker",
            backend_type="agent_mux",
            working_dir=str(self.agent_dir),
            config={
                "llm_proxy_url": f"http://127.0.0.1:{_free_port()}",
                "llm_proxy_api_key": "llm-proxy-key",
                "llm_route_policy": "codex_only",
                "model": "gpt-5.4",
                "agent_mux_binary": str(self.agent_mux_binary),
                "state_root": str(self.root / "runtime_state"),
                "max_attempts": max_attempts,
                "require_tool_call_for_response": require_tool_call_for_response,
                "mcp_servers": self._mcp_server_config() if include_mcp_server else [],
            },
            system_prompt="Use configured tools for external actions.",
            http_endpoint="http://orchestra-agent-generic_worker:8787",
        )
        await backend.on_start()
        return backend

    def _delivery(self, *, event_id: str = "event-1", message_text: str = "Prepare the update.") -> EventDelivery:
        return EventDelivery.from_dict(
            {
                "delivery_id": f"delivery-{event_id}",
                "events": [
                    {
                        "event_id": event_id,
                        "event_kind": "telegram_message",
                        "thread_id": None,
                        "root_thread_id": None,
                        "parent_thread_id": None,
                        "owner_agent_slug": None,
                        "sequence_no": None,
                        "notification_status": None,
                        "from_agent_slug": "telegram_ingress",
                        "to_agent_slug": "generic_worker",
                        "message_text": message_text,
                        "interrupts_runtime": True,
                        "requires_response": True,
                        "created_at": "2026-04-03T07:00:00Z",
                        "source_context": {
                            "channel": "telegram",
                            "chat_title": "Owner DM",
                            "sender_display": "Owner",
                            "received_at": "2026-04-03T07:00:00Z",
                        },
                    }
                ],
            }
        )

    async def test_direct_event_without_thread_id_runs_fake_agent_mux(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        backend = await self._start_backend(
            require_tool_call_for_response=True,
            include_mcp_server=True,
        )
        try:
            result = await backend.handle_events(self._delivery())
            self.assertTrue(result.accepted)
            completed = await _wait_for(lambda: backend.last_dispatch_status == "completed")
            self.assertTrue(completed)

            capture = json.loads(self.capture_path.read_text(encoding="utf-8"))
            self.assertEqual(capture["stdin_payload"]["engine"], "codex")
            self.assertEqual(capture["stdin_payload"]["role"], "worker")
            self.assertEqual(capture["stdin_payload"]["engine_opts"]["close_stdin_after_start"], True)
            self.assertEqual(capture["context_id_env"], backend.current_context_id)
            self.assertEqual(capture["event_id_env"], "event-1")
            self.assertEqual(capture["event_kind_env"], "telegram_message")
            self.assertEqual(capture["active_context"]["context_id"], backend.current_context_id)
            self.assertEqual(capture["active_context"]["event_id"], "event-1")
            self.assertNotIn("thread_id", capture["active_context"])
            self.assertEqual(capture["active_context"]["metadata"]["source_context"]["channel"], "telegram")
            self.assertEqual(capture["compat_active_context_path_env"], capture["active_context_path_env"])
            self.assertIn('model_provider = "llm_proxy"', capture["codex_config"])
            self.assertIn('[mcp_servers.orchestra_threads]', capture["codex_config"])
            self.assertIn('ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH', capture["codex_config"])

            status = await backend.last_status()
            self.assertEqual(status["context_id"], backend.current_context_id)
            self.assertEqual(status["runtime_context"]["context_id"], backend.current_context_id)
            self.assertEqual(status["last_dispatch_status"], "completed")
            self.assertEqual(status["last_processed_event_id"], "event-1")
            self.assertEqual(status["last_processed_event_kind"], "telegram_message")
            self.assertEqual(status["last_tool_calls"], ["mcp_tool_call"])
            self.assertEqual(status["runtime_state"]["queue_size"], 0)
        finally:
            await backend.on_shutdown()

    async def test_mcp_servers_are_optional(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        backend = await self._start_backend(
            require_tool_call_for_response=False,
            include_mcp_server=False,
        )
        try:
            await backend.handle_events(self._delivery())
            completed = await _wait_for(lambda: backend.last_dispatch_status == "completed")
            self.assertTrue(completed)
            capture = json.loads(self.capture_path.read_text(encoding="utf-8"))
            self.assertNotIn("[mcp_servers.", capture["codex_config"])
        finally:
            await backend.on_shutdown()

    async def test_sanitize_reply_text_strips_think_blocks(self) -> None:
        self.assertEqual(
            self.backend_module._sanitize_reply_text("<think>internal</think>\n\nREADY"),
            "READY",
        )

    async def test_plain_text_without_tool_call_is_rejected_when_policy_enabled(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "reply"
        backend = await self._start_backend(
            require_tool_call_for_response=True,
            max_attempts=1,
        )
        try:
            await backend.handle_events(self._delivery())
            failed = await _wait_for(
                lambda: (backend.last_dispatch_status == "failed" and backend.runtime_state.status_snapshot()["failed_queue_size"] == 1)
            )
            self.assertTrue(failed)
            self.assertIn("without any tool call", backend.last_dispatch_reason or "")
        finally:
            await backend.on_shutdown()

    async def test_stop_interrupts_active_dispatch(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "reply"
        os.environ["FAKE_AGENT_MUX_SLEEP"] = "5"
        backend = await self._start_backend()
        try:
            await backend.handle_events(self._delivery())
            active = await _wait_for(lambda: backend._active_process is not None and backend._active_process.returncode is None)
            self.assertTrue(active)
            stop_payload = await backend.stop(
                StopRequest(reason="stop requested", thread_id=None, parent_thread_id=None)
            )
            self.assertEqual(stop_payload["cleared_queue_events"], 0)
            cleared = await _wait_for(lambda: backend._active_process is None or backend._active_process.returncode is not None)
            self.assertTrue(cleared)
        finally:
            os.environ.pop("FAKE_AGENT_MUX_SLEEP", None)
            await backend.on_shutdown()

    async def test_context_id_persists_until_clear_context_and_survives_restart(self) -> None:
        backend = await self._start_backend()
        try:
            context_id_before = backend.current_context_id
            status_before = await backend.last_status()
            self.assertEqual(status_before["context_id"], context_id_before)
            self.assertEqual(status_before["runtime_context"]["recent_entries"], [])
        finally:
            await backend.on_shutdown()

        backend = await self._start_backend()
        try:
            self.assertEqual(backend.current_context_id, context_id_before)
            clear_payload = await backend.clear_context(self.backend_module.ClearContextRequest(requested_by="tester"))
            context_id_after = backend.current_context_id
            self.assertEqual(clear_payload["previous_context_id"], context_id_before)
            self.assertEqual(clear_payload["context_id"], context_id_after)
            self.assertNotEqual(context_id_after, context_id_before)
            self.assertEqual(clear_payload["runtime_context"]["context_id"], context_id_after)
            self.assertEqual(clear_payload["runtime_context"]["recent_entries"], [])
        finally:
            await backend.on_shutdown()

        backend = await self._start_backend()
        try:
            self.assertEqual(backend.current_context_id, context_id_after)
            status_after = await backend.last_status()
            self.assertEqual(status_after["runtime_context"]["context_id"], context_id_after)
            self.assertEqual(status_after["runtime_context"]["previous_context_id"], context_id_before)
            self.assertEqual(status_after["runtime_context"]["recent_entries"], [])
        finally:
            await backend.on_shutdown()

    async def test_context_memory_is_carried_across_turns_until_clear(self) -> None:
        os.environ["FAKE_AGENT_MUX_MODE"] = "tool_call"
        backend = await self._start_backend(
            require_tool_call_for_response=True,
        )
        try:
            await backend.handle_events(self._delivery(event_id="event-1", message_text="Prepare the update."))
            done = await _wait_for(lambda: backend.last_dispatch_status == "completed")
            self.assertTrue(done)

            await backend.handle_events(self._delivery(event_id="event-2", message_text="What did I ask before?"))
            done = await _wait_for(
                lambda: (
                    backend.last_dispatch_status == "completed"
                    and backend.last_processed_event_id == "event-2"
                    and len((backend.runtime_state.context_snapshot().get("recent_entries") or [])) >= 3
                )
            )
            self.assertTrue(done)
            capture = json.loads(self.capture_path.read_text(encoding="utf-8"))
            prompt = capture["stdin_payload"]["prompt"]
            self.assertIn("Prepare the update.", prompt)
            self.assertIn("What did I ask before?", prompt)
            self.assertIn("mcp_tool_call", prompt)

            status = await backend.last_status()
            recent_entries = status["runtime_context"]["recent_entries"]
            self.assertGreaterEqual(len(recent_entries), 3)
        finally:
            await backend.on_shutdown()
