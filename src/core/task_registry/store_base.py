from __future__ import annotations

import json
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_timestamp(value: Any) -> datetime | None:  # noqa: WPS212  # Timestamp normalization needs explicit branches.
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    normalized = str(value).strip()
    if not normalized:
        return None
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        parsed = parse_timestamp(value)
        if parsed is not None:
            return parsed.isoformat()
        return value.isoformat()
    return value


def row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key, value in list(payload.items()):
        normalized = normalize_value(value)
        payload[key] = normalized
        if isinstance(normalized, str) and key.endswith("_json"):
            try:
                payload[key] = json.loads(normalized)
            except json.JSONDecodeError:
                payload[key] = payload[key]
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


class TaskStoreBase:
    def __init__(
        self,
        database_url: str,
        *,
        schema_name: str = "public",
        min_pool_size: int = 5,
        max_pool_size: int = 20,
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
        if self.schema_name == "public":
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
