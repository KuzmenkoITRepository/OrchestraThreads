from __future__ import annotations

import json
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg

from core.orchestra_thread.store_clock import timestamp_within_lease as _timestamp_within_lease

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_MIN_POOL_SIZE = 5
DEFAULT_MAX_POOL_SIZE = 20
DEFAULT_COMMAND_TIMEOUT_SECONDS = 10.0


def parse_timestamp(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    normalized = str(raw_value).strip()
    if normalized:
        return datetime.fromisoformat(normalized)
    return None


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
        if isinstance(raw_value, str) and key.endswith("_json"):
            try:
                payload[key] = json.loads(raw_value)
            except json.JSONDecodeError:
                payload[key] = raw_value
            continue
        payload[key] = normalize_value(raw_value)
    return payload


def quote_ident(identifier: str) -> str:
    if not SCHEMA_NAME_RE.match(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


async def init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "json",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
    )
    await conn.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )


class ThreadStoreBase:
    def __init__(
        self,
        database_url: str,
        *,
        schema_name: str = "public",
        min_pool_size: int = DEFAULT_MIN_POOL_SIZE,
        max_pool_size: int = DEFAULT_MAX_POOL_SIZE,
        command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        if not self.database_url:
            raise ValueError("database_url is required")
        self.schema_name = str(schema_name or "public").strip() or "public"
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
                "application_name": "orchestra_threads",
                "search_path": self.schema_name,
            },
        )
        await self._ensure_schema()

    async def close(self) -> None:
        if self.pool is None:
            return
        await self.pool.close()
        self.pool = None

    async def drop_schema(self) -> None:
        if self.schema_name == "public":
            return
        conn = await asyncpg.connect(
            dsn=self.database_url,
            command_timeout=self.command_timeout_seconds,
        )
        await conn.execute(f"DROP SCHEMA IF EXISTS {quote_ident(self.schema_name)} CASCADE")
        with suppress(Exception):
            await conn.close()

    async def ping(self) -> bool:
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            return False
        return True

    def timestamp_within_lease(self, value: Any, *, lease_seconds: int) -> bool:
        return _timestamp_within_lease(value, lease_seconds=lease_seconds)

    async def _ensure_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(self.schema_name)}")
            await conn.execute(f"SET search_path TO {quote_ident(self.schema_name)}")
            await conn.execute(SCHEMA_SQL)
