from __future__ import annotations

import unittest

from core.telegram_events.agent_registry import RegistrationStatus, TelegramAgentRegistry


class TelegramAgentRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = TelegramAgentRegistry()

    def test_register_normalizes_inputs_and_derives_events_url(self) -> None:
        result = self.registry.register("  assistant-alpha  ", "  http://example.test/mcp/  ")

        self.assertEqual(result.status, RegistrationStatus.REGISTERED)
        self.assertEqual(result.agent_slug, "assistant-alpha")
        self.assertEqual(result.telegram_mcp_url, "http://example.test/mcp")
        self.assertEqual(result.events_url, "http://example.test/events/telegram")
        self.assertEqual(
            self.registry.get_slug_for_mcp_url("http://example.test/mcp/"), "assistant-alpha"
        )
        self.assertEqual(
            self.registry.get_events_url_for_mcp_url("http://example.test/mcp/"),
            "http://example.test/events/telegram",
        )

    def test_register_duplicate_same_slug_and_url_is_idempotent(self) -> None:
        first = self.registry.register("assistant-alpha", "http://example.test/mcp/")
        second = self.registry.register(" assistant-alpha ", "http://example.test/mcp")

        self.assertEqual(first.status, RegistrationStatus.REGISTERED)
        self.assertEqual(second.status, RegistrationStatus.DUPLICATE)
        self.assertEqual(
            self.registry.get_slug_for_mcp_url("http://example.test/mcp"), "assistant-alpha"
        )

    def test_register_conflict_different_slug_same_url_does_not_replace_owner(self) -> None:
        self.registry.register("assistant-alpha", "http://example.test/mcp")

        result = self.registry.register("assistant-beta", "http://example.test/mcp/")

        self.assertEqual(result.status, RegistrationStatus.CONFLICT)
        self.assertEqual(result.conflicting_agent_slug, "assistant-alpha")
        self.assertEqual(
            self.registry.get_slug_for_mcp_url("http://example.test/mcp"), "assistant-alpha"
        )
        self.assertIsNone(self.registry.get_registration_for_slug("assistant-beta"))

    def test_register_same_slug_new_url_returns_remap_metadata(self) -> None:
        first = self.registry.register("assistant-alpha", "http://old.example.test/mcp/")
        second = self.registry.register("assistant-alpha", "http://new.example.test/mcp/")

        self.assertEqual(first.status, RegistrationStatus.REGISTERED)
        self.assertEqual(second.status, RegistrationStatus.REMAPPED)
        self.assertEqual(second.previous_telegram_mcp_url, "http://old.example.test/mcp")
        self.assertEqual(second.previous_events_url, "http://old.example.test/events/telegram")
        self.assertEqual(
            self.registry.get_slug_for_mcp_url("http://new.example.test/mcp"), "assistant-alpha"
        )
        self.assertIsNone(self.registry.get_slug_for_mcp_url("http://old.example.test/mcp"))

    def test_register_same_slug_new_url_updates_registration_record(self) -> None:
        self.registry.register("assistant-alpha", "http://old.example.test/mcp")
        self.registry.register("assistant-alpha", "http://new.example.test/mcp")

        registration = self.registry.get_registration_for_slug("assistant-alpha")
        if registration is None:
            self.fail("registration should exist")

        self.assertEqual(
            registration.telegram_mcp_url,
            "http://new.example.test/mcp",
        )
        self.assertEqual(
            registration.events_url,
            "http://new.example.test/events/telegram",
        )


if __name__ == "__main__":
    unittest.main()
