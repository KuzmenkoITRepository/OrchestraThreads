from __future__ import annotations

from importlib import import_module
from unittest import TestCase

backend_profiles = import_module("core.orchestra_agents.launch.backend_profiles")


class BackendProfilesTests(TestCase):
    def test_known_backend_profile_defaults(self) -> None:
        profile = backend_profiles.backend_profile("agent_mux")

        assert profile is not None
        self.assertEqual(profile.image, "orchestra-agent-mux-runtime:latest")
        self.assertEqual(
            profile.command,
            ("python", "-m", "core.orchestra_agents.backends.agent_mux.main"),
        )
        self.assertEqual(profile.build_dockerfile, "docker/backends/agent_mux/Dockerfile")
        self.assertEqual(profile.env["PYTHONPATH"], "/workspace/src")
        self.assertIn("OMNIROUTE_URL", profile.env_passthrough)

    def test_local_runtime_dockerfile_uses_build(self) -> None:
        self.assertEqual(
            backend_profiles.local_runtime_dockerfile("orchestra-opencode-runtime:latest"),
            "docker/backends/opencode/Dockerfile",
        )

    def test_merge_env_passthrough_keeps_order(self) -> None:
        merged = backend_profiles.merge_env_passthrough(
            ("LOG_LEVEL", "OMNIROUTE_URL"),
            ("OMNIROUTE_URL", "OPENAI_API_KEY"),
        )

        self.assertEqual(merged, ("LOG_LEVEL", "OMNIROUTE_URL", "OPENAI_API_KEY"))
