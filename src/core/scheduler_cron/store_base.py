from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import asyncpg

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(identifier: str) -> str:
    if not SCHEMA_NAME_RE.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def normalize_value(raw_value: object) -> object:
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC).isoformat()
        return raw_value.astimezone(UTC).isoformat()
    return raw_value


def row_to_dict(row: asyncpg.Record | None) -> dict[str, object] | None:  # type: ignore[no-any-unimported]  # asyncpg stub
    if row is None:
        return None
    payload = dict(row)
    for key, raw_value in list(payload.items()):
        payload[key] = normalize_value(raw_value)
    return payload


def rows_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, object]]:  # type: ignore[no-any-unimported]  # asyncpg stub
    payloads: list[dict[str, object]] = []
    for row in rows:
        payload = row_to_dict(row)
        if payload is not None:
            payloads.append(payload)
    return payloads


async def init_connection(conn: asyncpg.Connection) -> None:  # type: ignore[no-any-unimported]  # asyncpg stub
    await conn.set_type_codec("json", schema="pg_catalog", encoder=json.dumps, decoder=json.loads)
    await conn.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )


class SchedulerCronStoreBase:
    def __init__(
        self,
        database_url: str,
        *,
        schema_name: str = "public",
        min_pool_size: int = 1,
        max_pool_size: int = 5,
        command_timeout_seconds: float = 10.0,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        if not self.database_url:
            raise ValueError("database_url is required")
        self.schema_name = str(schema_name or "public").strip() or "public"
        quote_ident(self.schema_name)
        self.min_pool_size = max(1, int(min_pool_size))
        self.max_pool_size = max(self.min_pool_size, int(max_pool_size))
        self.command_timeout_seconds = max(1.0, float(command_timeout_seconds))
        self.pool: asyncpg.Pool | None = None  # type: ignore[no-any-unimported]  # asyncpg stub

    async def start(self) -> None:
        if self.pool is not None:
            return
        self.pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
            command_timeout=self.command_timeout_seconds,
            init=init_connection,
            server_settings={"application_name": "scheduler_cron", "search_path": self.schema_name},
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

    async def _ensure_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(self.schema_name)}")
            await conn.execute(f"SET search_path TO {quote_ident(self.schema_name)}")
            await conn.execute(SCHEMA_SQL)


class SupportsSchedulerCronPool(Protocol):
    pool: asyncpg.Pool | None  # type: ignore[no-any-unimported]  # asyncpg stub
