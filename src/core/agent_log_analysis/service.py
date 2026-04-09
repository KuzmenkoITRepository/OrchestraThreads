"""Thin facade for the agent log analysis service."""

from __future__ import annotations

from core.agent_log_analysis import service_runtime

AgentLogAnalysisService = service_runtime.AgentLogAnalysisService
build_app = service_runtime.build_app
run_service = service_runtime.run_service
