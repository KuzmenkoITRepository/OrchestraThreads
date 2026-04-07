from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from unittest import TestCase
from unittest.mock import patch

from core.scheduler_cron.config import SchedulerCronConfig, load_config


class TestLoadConfig(TestCase):
    def _base_env(self) -> dict[str, str]:
        return {
            "SCHEDULER_CRON_HOST": "127.0.0.1",
            "SCHEDULER_CRON_PORT": "9000",
            "SCHEDULER_CRON_DATABASE_URL": "postgresql://user:pass@db:5432/app",
            "SCHEDULER_CRON_DB_SCHEMA": "scheduler",
        }

    def test_loads_all_environment_variables(self) -> None:
        env = self._base_env()
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9000)
        self.assertEqual(config.database_url, "postgresql://user:pass@db:5432/app")
        self.assertEqual(config.db_schema, "scheduler")

    def test_uses_default_host_when_not_set(self) -> None:
        env = self._base_env()
        del env["SCHEDULER_CRON_HOST"]
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.host, "0.0.0.0")

    def test_uses_default_port_when_not_set(self) -> None:
        env = self._base_env()
        del env["SCHEDULER_CRON_PORT"]
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.port, 8792)

    def test_uses_default_schema_when_not_set(self) -> None:
        env = self._base_env()
        del env["SCHEDULER_CRON_DB_SCHEMA"]
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.db_schema, "public")

    def test_missing_database_url_raises_value_error(self) -> None:
        env = self._base_env()
        del env["SCHEDULER_CRON_DATABASE_URL"]

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                load_config()

    def test_empty_database_url_raises_value_error(self) -> None:
        env = self._base_env()
        env["SCHEDULER_CRON_DATABASE_URL"] = "   "

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                load_config()

    def test_port_is_parsed_as_int(self) -> None:
        env = self._base_env()
        env["SCHEDULER_CRON_PORT"] = "9011"

        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertIsInstance(config.port, int)
        self.assertEqual(config.port, 9011)

    def test_config_is_frozen_dataclass(self) -> None:
        env = self._base_env()
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertIsInstance(config, SchedulerCronConfig)
        with self.assertRaises(FrozenInstanceError):
            config.port = 42  # type: ignore[misc]  # intentional: verifying frozen dataclass rejects mutation
