"""Tests for store composition root."""

from __future__ import annotations

import unittest

from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_base import LogStoreBase


class TestStoreComposition(unittest.TestCase):
    """Verify composition root is thin and inherits correctly."""

    def test_inherits_base(self) -> None:
        self.assertTrue(issubclass(LogStore, LogStoreBase))

    def test_no_extra_public_attrs(self) -> None:
        LogStore(database_url="postgresql://x")
        self.assertFalse(
            hasattr(LogStore, "__dict__")
            and any(
                not k.startswith("_") for k in LogStore.__dict__ if k not in LogStoreBase.__dict__
            ),
            "LogStore should not add new public methods",
        )

    def test_has_slots(self) -> None:
        self.assertEqual(LogStore.__slots__, ())

    def test_instantiation(self) -> None:
        store = LogStore(database_url="postgresql://x")
        self.assertIsInstance(store, LogStoreBase)
        self.assertIsInstance(store, LogStore)
