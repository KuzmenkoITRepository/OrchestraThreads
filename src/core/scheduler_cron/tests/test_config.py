from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from unittest import TestCase
from unittest.mock import patch

from core.scheduler_cron.config import SchedulerCronConfig, load_config

_EXPECTED_HOST = "127.0.0.1"
_DEFAULT_PORT = 8792
_TEST_PORT = 9000
_OVERRIDE_PORT = 9011
_DATABASE_URL = "postgresql://user:pass@db:5432/app"


class TestLoadConfig(TestCase):  # noqa: WPS214 - config has many env-var scenarios requiring individual test methods
    def test_loads_all_environment_variables(self) -> None:
        with self._clean_env():
            config = load_config()

        self.assertEqual(config.host, _EXPECTED_HOST)
        self.assertEqual(config.port, _TEST_PORT)
        self.assertEqual(config.database_url, _DATABASE_URL)
        self.assertEqual(config.db_schema, "scheduler")

    def test_uses_default_host_when_not_set(self) -> None:
        with self._clean_env("SCHEDULER_CRON_HOST"):
            config = load_config()

        self.assertEqual(config.host, "0.0.0.0")

    def test_uses_default_port_when_not_set(self) -> None:
        with self._clean_env("SCHEDULER_CRON_PORT"):
            config = load_config()

        self.assertEqual(config.port, _DEFAULT_PORT)

    def test_uses_default_schema_when_not_set(self) -> None:
        with self._clean_env("SCHEDULER_CRON_DB_SCHEMA"):
            config = load_config()

        self.assertEqual(config.db_schema, "public")

    def test_missing_database_url_raises(self) -> None:
        with self._clean_env("SCHEDULER_CRON_DATABASE_URL"):
            with self.assertRaises(ValueError):
                load_config()

    def test_empty_database_url_raises(self) -> None:
        with self._clean_env(set_blank="SCHEDULER_CRON_DATABASE_URL"):
            with self.assertRaises(ValueError):
                load_config()

    def test_port_is_parsed_as_int(self) -> None:
        with self._clean_env(set_override=("SCHEDULER_CRON_PORT", "9011")):
            config = load_config()

        self.assertIsInstance(config.port, int)
        self.assertEqual(config.port, _OVERRIDE_PORT)

    def test_config_is_frozen_dataclass(self) -> None:
        with self._clean_env():
            config = load_config()

        self.assertIsInstance(config, SchedulerCronConfig)
        with self.assertRaises(FrozenInstanceError):
            config.port = 42  # type: ignore[misc]  # intentional: verifying frozen dataclass rejects mutation

    @contextmanager
    def _clean_env(
        self,
        drop_key: str | None = None,
        *,
        set_blank: str | None = None,
        set_override: tuple[str, str] | None = None,
    ) -> Iterator[None]:
        env: dict[str, str] = {
            "SCHEDULER_CRON_HOST": _EXPECTED_HOST,
            "SCHEDULER_CRON_PORT": str(_TEST_PORT),
            "SCHEDULER_CRON_DATABASE_URL": _DATABASE_URL,
            "SCHEDULER_CRON_DB_SCHEMA": "scheduler",
        }
        if drop_key is not None:
            env.pop(drop_key)
        if set_blank is not None:
            env[set_blank] = "   "
        if set_override is not None:
            env[set_override[0]] = set_override[1]
        with patch.dict(os.environ, env, clear=True):
            yield
