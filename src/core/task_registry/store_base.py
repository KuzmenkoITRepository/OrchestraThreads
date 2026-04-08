from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, cast

import asyncpg

from core.task_registry.store_base_sql import SCHEMA_SQL, init_connection, quote_ident

DEFAULT_SCHEMA_NAME = "public"


def parse_timestamp(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return _normalize_datetime(raw_value)
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    parsed = datetime.fromisoformat(normalized)
    return _normalize_datetime(parsed)


def normalize_value(raw_value: Any) -> Any:
    if isinstance(raw_value, datetime):
        parsed = parse_timestamp(raw_value)
        if parsed is not None:
            return parsed.isoformat()
        return raw_value.isoformat()
    return raw_value


def row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key, raw_value in list(payload.items()):
        normalized = normalize_value(raw_value)
        payload[key] = normalized
        if isinstance(normalized, str) and key.endswith("_json"):
            parsed_json = _parse_json_text(normalized)
            if parsed_json is not None:
                payload[key] = parsed_json
    return payload


def _normalize_datetime(raw_value: datetime) -> datetime:
    if raw_value.tzinfo is None:
        return raw_value.replace(tzinfo=UTC)
    return raw_value.astimezone(UTC)


def _parse_json_text(normalized: str) -> object | None:
    try:
        return cast(object, json.loads(normalized))
    except json.JSONDecodeError:
        return None


class TaskStoreBase:
    def __init__(
        self,
        database_url: str,
        *,
        schema_name: str = DEFAULT_SCHEMA_NAME,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
        command_timeout_seconds: float = 10.0,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        if not self.database_url:
            raise ValueError("database_url is required")
        self.schema_name = str(schema_name or DEFAULT_SCHEMA_NAME).strip() or DEFAULT_SCHEMA_NAME
        quote_ident(self.schema_name)
        self.min_pool_size = max(1, int(min_pool_size))
        self.max_pool_size = max(self.min_pool_size, int(max_pool_size))
        self.command_timeout_seconds = max(1.0, float(command_timeout_seconds))
        self.pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        if self.pool is not None:
            return
        self.pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
            command_timeout=self.command_timeout_seconds,
            init=init_connection,
            server_settings={
                "application_name": "task_registry",
                "search_path": self.schema_name,
            },
        )
        await self._ensure_schema()

    async def close(self) -> None:
        if self.pool is None:
            return
        await self.pool.close()
        self.pool = None

    async def ping(self) -> bool:
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            return False
        return True

    async def drop_schema(self) -> None:
        if self.schema_name == DEFAULT_SCHEMA_NAME:
            return
        conn: asyncpg.Connection | None = None
        try:
            conn = await asyncpg.connect(
                dsn=self.database_url,
                command_timeout=self.command_timeout_seconds,
            )
        except Exception:
            raise
        assert conn is not None
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {quote_ident(self.schema_name)} CASCADE")
        except Exception:
            raise
        finally:
            with suppress(Exception):
                if conn is not None:
                    await conn.close()

    async def _ensure_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(self.schema_name)}")
            await conn.execute(f"SET search_path TO {quote_ident(self.schema_name)}")
            await conn.execute(SCHEMA_SQL)
