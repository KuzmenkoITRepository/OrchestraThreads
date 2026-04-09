"""Asyncpg-backed base class for the agent log analysis store."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import cast

import asyncpg

from core.agent_log_analysis.store_base_sql import (
    SCHEMA_SQL,
    init_connection,
    quote_ident,
)
from core.agent_log_analysis.store_protocols import (
    SchemaCleanupConnectionProtocol,
    StorePoolProtocol,
)

DEFAULT_SCHEMA_NAME = "agent_log_analysis"


class LogStoreBase:
    """Base persistence layer with pool lifecycle and schema bootstrap."""

    def __init__(
        self,
        database_url: str,
        *,
        schema_name: str = DEFAULT_SCHEMA_NAME,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
        command_timeout_seconds: float = 10.0,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        if not self.database_url:
            raise ValueError("database_url is required")
        self.schema_name = _resolve_schema(schema_name)
        quote_ident(self.schema_name)
        self.min_pool_size = max(1, int(min_pool_size))
        self.max_pool_size = max(self.min_pool_size, int(max_pool_size))
        self.command_timeout_seconds = max(1.0, float(command_timeout_seconds))
        self.pool: StorePoolProtocol | None = None

    async def start(self) -> None:
        """Create the connection pool and bootstrap the schema."""
        if self.pool is not None:
            return
        self.pool = cast(
            StorePoolProtocol,
            await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                command_timeout=self.command_timeout_seconds,
                init=init_connection,
                server_settings={
                    "application_name": "agent_log_analysis",
                    "search_path": self.schema_name,
                },
            ),
        )
        await self._ensure_schema()

    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool is None:
            return
        await self.pool.close()
        self.pool = None

    async def ping(self) -> bool:
        """Check pool connectivity."""
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            return False
        return True

    async def drop_schema(self) -> None:
        """Drop the schema (test cleanup only)."""
        if self.schema_name == DEFAULT_SCHEMA_NAME:
            return
        async with _connect_for_schema_cleanup(
            database_url=self.database_url,
            command_timeout_seconds=self.command_timeout_seconds,
        ) as conn:
            await conn.execute(
                f"DROP SCHEMA IF EXISTS {quote_ident(self.schema_name)} CASCADE",
            )

    async def _ensure_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"CREATE SCHEMA IF NOT EXISTS {quote_ident(self.schema_name)}",
            )
            await conn.execute(
                f"SET search_path TO {quote_ident(self.schema_name)}",
            )
            await conn.execute(SCHEMA_SQL)


def _resolve_schema(schema_name: str) -> str:
    cleaned = str(schema_name or DEFAULT_SCHEMA_NAME).strip()
    return cleaned or DEFAULT_SCHEMA_NAME


@asynccontextmanager
async def _connect_for_schema_cleanup(
    *,
    database_url: str,
    command_timeout_seconds: float,
) -> AsyncIterator[SchemaCleanupConnectionProtocol]:
    connection = cast(
        SchemaCleanupConnectionProtocol,
        await asyncpg.connect(
            dsn=database_url,
            command_timeout=command_timeout_seconds,
        ),
    )
    try:
        yield connection
    finally:
        with suppress(Exception):
            await connection.close()
