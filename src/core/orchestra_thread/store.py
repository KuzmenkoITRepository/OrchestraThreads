"""Postgres-backed persistence for OrchestraThreads."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg

from .common import THREAD_TERMINAL_STATUSES, normalize_participants, normalize_status

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    normalized = str(value).strip()
    if not normalized:
        return None
    return datetime.fromisoformat(normalized)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _parse_timestamp(value).isoformat()
    return value


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key, value in list(payload.items()):
        if isinstance(value, str) and key.endswith("_json"):
            try:
                payload[key] = json.loads(value)
            except json.JSONDecodeError:
                payload[key] = value
            continue
        payload[key] = _normalize_value(value)
    return payload


def _quote_ident(identifier: str) -> str:
    if not SCHEMA_NAME_RE.match(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _rowcount_from_status(status_text: str) -> int:
    parts = str(status_text or "").split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except ValueError:
        return 0


async def _init_connection(conn: asyncpg.Connection) -> None:
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


class ThreadStore:
    """Async Postgres store wrapped by the OrchestraThreads service."""

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
        _quote_ident(self.schema_name)
        self.min_pool_size = max(1, int(min_pool_size))
        self.max_pool_size = max(self.min_pool_size, int(max_pool_size))
        self.command_timeout_seconds = max(1.0, float(command_timeout_seconds))
        self.pool: asyncpg.Pool | None = None

    @staticmethod
    def timestamp_within_lease(value: Any, *, lease_seconds: int) -> bool:
        parsed = _parse_timestamp(value)
        if parsed is None:
            return False
        return datetime.now(UTC) - parsed <= timedelta(seconds=lease_seconds)

    async def start(self) -> None:
        if self.pool is not None:
            return
        self.pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
            command_timeout=self.command_timeout_seconds,
            init=_init_connection,
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
            dsn=self.database_url, command_timeout=self.command_timeout_seconds
        )
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {_quote_ident(self.schema_name)} CASCADE")
        finally:
            await conn.close()

    async def ping(self) -> bool:
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def _ensure_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote_ident(self.schema_name)}")
            await conn.execute(f"SET search_path TO {_quote_ident(self.schema_name)}")
            await conn.execute(SCHEMA_SQL)

    async def upsert_agent(
        self,
        *,
        agent_slug: str,
        display_name: str,
        event_callback_url: str,
        stop_callback_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO agents (
                    agent_slug,
                    display_name,
                    event_callback_url,
                    stop_callback_url,
                    metadata_json,
                    registered_at,
                    last_seen_at
                ) VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
                ON CONFLICT(agent_slug) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    event_callback_url = EXCLUDED.event_callback_url,
                    stop_callback_url = EXCLUDED.stop_callback_url,
                    metadata_json = EXCLUDED.metadata_json,
                    last_seen_at = EXCLUDED.last_seen_at
                RETURNING *
                """,
                agent_slug,
                display_name,
                event_callback_url,
                stop_callback_url,
                metadata,
            )
        return _row_to_dict(row) or {}

    async def touch_agent(self, *, agent_slug: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE agents
                SET last_seen_at = NOW()
                WHERE agent_slug = $1
                RETURNING *
                """,
                agent_slug,
            )
        return _row_to_dict(row)

    async def get_agent(self, agent_slug: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM agents
                WHERE agent_slug = $1
                """,
                agent_slug,
            )
        return _row_to_dict(row)

    async def list_agents(self) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM agents
                ORDER BY agent_slug ASC
                """
            )
        return [_row_to_dict(row) for row in rows if row is not None]

    async def get_idempotent_result(
        self, *, from_agent_slug: str, client_request_id: str
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT response_json
                FROM idempotency_keys
                WHERE from_agent_slug = $1 AND client_request_id = $2
                """,
                from_agent_slug,
                client_request_id,
            )
        if row is None:
            return None
        payload = row["response_json"]
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload) if isinstance(payload, dict) else payload

    async def save_idempotent_result(
        self,
        *,
        from_agent_slug: str,
        client_request_id: str,
        operation_name: str,
        response_payload: dict[str, Any],
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO idempotency_keys (
                    from_agent_slug,
                    client_request_id,
                    operation_name,
                    response_json,
                    created_at
                ) VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (from_agent_slug, client_request_id) DO NOTHING
                """,
                from_agent_slug,
                client_request_id,
                operation_name,
                response_payload,
            )

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM threads
                WHERE thread_id = $1
                """,
                thread_id,
            )
        return _row_to_dict(row)

    async def list_threads(self, *, active_only: bool, limit: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        sql = """
            SELECT
                t.*,
                COALESCE(stats.event_count, 0) AS event_count,
                COALESCE(stats.pending_delivery_count, 0) AS pending_delivery_count,
                COALESCE(children.child_thread_count, 0) AS child_thread_count,
                last_event.event_id AS last_event_id,
                last_event.sequence_no AS last_event_sequence_no,
                last_event.event_kind AS last_event_kind,
                last_event.notification_status AS last_event_notification_status,
                last_event.from_agent_slug AS last_event_from_agent_slug,
                last_event.to_agent_slug AS last_event_to_agent_slug,
                last_event.message_text AS last_event_message_text,
                last_event.created_at AS last_event_created_at,
                last_event.pending_delivery AS last_event_pending_delivery
            FROM threads t
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) AS event_count,
                    COUNT(*) FILTER (WHERE pending_delivery = TRUE) AS pending_delivery_count
                FROM thread_events
                WHERE thread_id = t.thread_id
            ) stats ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS child_thread_count
                FROM threads child
                WHERE child.parent_thread_id = t.thread_id
            ) children ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    event_id,
                    sequence_no,
                    event_kind,
                    notification_status,
                    from_agent_slug,
                    to_agent_slug,
                    message_text,
                    created_at,
                    pending_delivery
                FROM thread_events
                WHERE thread_id = t.thread_id
                ORDER BY sequence_no DESC
                LIMIT 1
            ) last_event ON TRUE
        """
        if active_only:
            sql += " WHERE t.status NOT IN ('done', 'closed')"
        sql += """
            ORDER BY
                CASE WHEN t.status IN ('done', 'closed') THEN 1 ELSE 0 END ASC,
                COALESCE(t.last_activity_at, t.updated_at, t.created_at) DESC,
                t.created_at DESC
            LIMIT $1
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, max(1, limit))
        return [_row_to_dict(row) for row in rows if row is not None]

    async def list_threads_by_root(self, *, root_thread_id: str) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    t.*,
                    COALESCE(stats.event_count, 0) AS event_count,
                    COALESCE(stats.pending_delivery_count, 0) AS pending_delivery_count,
                    COALESCE(children.child_thread_count, 0) AS child_thread_count,
                    last_event.event_id AS last_event_id,
                    last_event.sequence_no AS last_event_sequence_no,
                    last_event.event_kind AS last_event_kind,
                    last_event.notification_status AS last_event_notification_status,
                    last_event.from_agent_slug AS last_event_from_agent_slug,
                    last_event.to_agent_slug AS last_event_to_agent_slug,
                    last_event.message_text AS last_event_message_text,
                    last_event.created_at AS last_event_created_at,
                    last_event.pending_delivery AS last_event_pending_delivery
                FROM threads t
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS event_count,
                        COUNT(*) FILTER (WHERE pending_delivery = TRUE) AS pending_delivery_count
                    FROM thread_events
                    WHERE thread_id = t.thread_id
                ) stats ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS child_thread_count
                    FROM threads child
                    WHERE child.parent_thread_id = t.thread_id
                ) children ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        event_id,
                        sequence_no,
                        event_kind,
                        notification_status,
                        from_agent_slug,
                        to_agent_slug,
                        message_text,
                        created_at,
                        pending_delivery
                    FROM thread_events
                    WHERE thread_id = t.thread_id
                    ORDER BY sequence_no DESC
                    LIMIT 1
                ) last_event ON TRUE
                WHERE t.root_thread_id = $1
                ORDER BY CASE WHEN t.thread_id = t.root_thread_id THEN 0 ELSE 1 END, t.created_at ASC
                """,
                root_thread_id,
            )
        return [_row_to_dict(row) for row in rows if row is not None]

    async def list_child_threads(self, *, parent_thread_id: str) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM threads
                WHERE parent_thread_id = $1
                ORDER BY created_at ASC
                """,
                parent_thread_id,
            )
        return [_row_to_dict(row) for row in rows if row is not None]

    async def list_thread_events(self, *, thread_id: str, limit: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM thread_events
                WHERE thread_id = $1
                ORDER BY sequence_no ASC
                LIMIT $2
                """,
                thread_id,
                max(1, limit),
            )
        return [_row_to_dict(row) for row in rows if row is not None]

    async def get_latest_thread_event(self, *, thread_id: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM thread_events
                WHERE thread_id = $1
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                thread_id,
            )
        return _row_to_dict(row)

    async def get_or_create_root_thread(
        self,
        *,
        thread_id: str,
        owner_agent_slug: str,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[dict[str, Any], bool]:
        assert self.pool is not None
        participant_a, participant_b = normalize_participants(from_agent_slug, to_agent_slug)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    """
                    SELECT *
                    FROM threads
                    WHERE parent_thread_id IS NULL
                      AND participant_a_agent_slug = $1
                      AND participant_b_agent_slug = $2
                      AND status NOT IN ('done', 'closed')
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    participant_a,
                    participant_b,
                )
                if existing is not None:
                    return _row_to_dict(existing) or {}, False
                try:
                    created = await conn.fetchrow(
                        """
                        INSERT INTO threads (
                            thread_id,
                            root_thread_id,
                            parent_thread_id,
                            owner_agent_slug,
                            participant_a_agent_slug,
                            participant_b_agent_slug,
                            status,
                            last_sequence_no,
                            created_at,
                            updated_at
                        ) VALUES ($1, $1, NULL, $2, $3, $4, 'open', 0, NOW(), NOW())
                        RETURNING *
                        """,
                        thread_id,
                        owner_agent_slug,
                        participant_a,
                        participant_b,
                    )
                    return _row_to_dict(created) or {}, True
                except asyncpg.UniqueViolationError:
                    existing = await conn.fetchrow(
                        """
                        SELECT *
                        FROM threads
                        WHERE parent_thread_id IS NULL
                          AND participant_a_agent_slug = $1
                          AND participant_b_agent_slug = $2
                          AND status NOT IN ('done', 'closed')
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT 1
                        """,
                        participant_a,
                        participant_b,
                    )
                    if existing is not None:
                        return _row_to_dict(existing) or {}, False
                    raise

    async def get_or_create_child_thread(
        self,
        *,
        thread_id: str,
        root_thread_id: str,
        parent_thread_id: str,
        owner_agent_slug: str,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[dict[str, Any], bool]:
        assert self.pool is not None
        participant_a, participant_b = normalize_participants(from_agent_slug, to_agent_slug)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    """
                    SELECT *
                    FROM threads
                    WHERE parent_thread_id = $1
                      AND participant_a_agent_slug = $2
                      AND participant_b_agent_slug = $3
                      AND status NOT IN ('done', 'closed')
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    parent_thread_id,
                    participant_a,
                    participant_b,
                )
                if existing is not None:
                    return _row_to_dict(existing) or {}, False
                try:
                    created = await conn.fetchrow(
                        """
                        INSERT INTO threads (
                            thread_id,
                            root_thread_id,
                            parent_thread_id,
                            owner_agent_slug,
                            participant_a_agent_slug,
                            participant_b_agent_slug,
                            status,
                            last_sequence_no,
                            created_at,
                            updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, 'open', 0, NOW(), NOW())
                        RETURNING *
                        """,
                        thread_id,
                        root_thread_id,
                        parent_thread_id,
                        owner_agent_slug,
                        participant_a,
                        participant_b,
                    )
                    return _row_to_dict(created) or {}, True
                except asyncpg.UniqueViolationError:
                    existing = await conn.fetchrow(
                        """
                        SELECT *
                        FROM threads
                        WHERE parent_thread_id = $1
                          AND participant_a_agent_slug = $2
                          AND participant_b_agent_slug = $3
                          AND status NOT IN ('done', 'closed')
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT 1
                        """,
                        parent_thread_id,
                        participant_a,
                        participant_b,
                    )
                    if existing is not None:
                        return _row_to_dict(existing) or {}, False
                    raise

    async def append_thread_event(
        self,
        *,
        event_id: str,
        thread_id: str,
        event_kind: str,
        notification_status: str | None,
        from_agent_slug: str,
        to_agent_slug: str,
        message_text: str,
        interrupts_runtime: bool,
        requires_response: bool,
        touch_activity: bool,
        update_last_message_sender: bool,
        set_thread_status: str | None = None,
        set_terminal: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                thread = await conn.fetchrow(
                    """
                    SELECT *
                    FROM threads
                    WHERE thread_id = $1
                    FOR UPDATE
                    """,
                    thread_id,
                )
                if thread is None:
                    raise KeyError(f"Unknown thread_id: {thread_id}")
                if normalize_status(str(thread["status"] or "")) in THREAD_TERMINAL_STATUSES:
                    raise ValueError(f"Thread {thread_id} is already terminal")

                now = datetime.now(UTC)
                next_sequence = int(thread["last_sequence_no"] or 0) + 1
                event = await conn.fetchrow(
                    """
                    INSERT INTO thread_events (
                        event_id,
                        thread_id,
                        sequence_no,
                        event_kind,
                        notification_status,
                        from_agent_slug,
                        to_agent_slug,
                        message_text,
                        interrupts_runtime,
                        requires_response,
                        pending_delivery,
                        delivery_attempt_count,
                        next_delivery_attempt_at,
                        delivered_at,
                        last_delivery_error,
                        created_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $9, 0,
                        CASE WHEN $9 THEN $11::timestamptz ELSE NULL::timestamptz END,
                        NULL,
                        NULL,
                        $11
                    )
                    RETURNING *
                    """,
                    event_id,
                    thread_id,
                    next_sequence,
                    event_kind,
                    notification_status,
                    from_agent_slug,
                    to_agent_slug,
                    message_text,
                    interrupts_runtime,
                    requires_response,
                    now,
                )
                thread_payload = await conn.fetchrow(
                    """
                    UPDATE threads
                    SET updated_at = $1,
                        status = COALESCE($2, status),
                        last_activity_at = CASE WHEN $3 THEN $1 ELSE last_activity_at END,
                        last_message_sender_agent_slug = CASE WHEN $4 THEN $5 ELSE last_message_sender_agent_slug END,
                        terminal_at = CASE WHEN $6 THEN COALESCE(terminal_at, $1) ELSE terminal_at END,
                        last_sequence_no = $7
                    WHERE thread_id = $8
                    RETURNING *
                    """,
                    now,
                    set_thread_status,
                    touch_activity,
                    update_last_message_sender,
                    from_agent_slug,
                    set_terminal,
                    next_sequence,
                    thread_id,
                )
        return (_row_to_dict(event) or {}, _row_to_dict(thread_payload) or {})

    async def list_due_pending_events(self, *, now_iso: str, limit: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        now = _parse_timestamp(now_iso) or datetime.now(UTC)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    e.*,
                    t.root_thread_id,
                    t.parent_thread_id,
                    t.owner_agent_slug,
                    t.status AS thread_status,
                    a.event_callback_url,
                    a.last_seen_at AS agent_last_seen_at,
                    a.stop_callback_url
                FROM thread_events e
                JOIN threads t ON t.thread_id = e.thread_id
                LEFT JOIN agents a ON a.agent_slug = e.to_agent_slug
                WHERE e.pending_delivery = TRUE
                  AND t.status NOT IN ('done', 'closed')
                  AND COALESCE(e.next_delivery_attempt_at, e.created_at) <= $1
                ORDER BY COALESCE(e.next_delivery_attempt_at, e.created_at) ASC, e.created_at ASC, e.sequence_no ASC
                LIMIT $2
                """,
                now,
                max(1, limit),
            )
        return [_row_to_dict(row) for row in rows if row is not None]

    async def mark_event_delivered(self, *, event_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE thread_events
                SET pending_delivery = FALSE,
                    delivered_at = NOW(),
                    next_delivery_attempt_at = NULL,
                    last_delivery_error = NULL
                WHERE event_id = $1
                """,
                event_id,
            )

    async def mark_event_failed(
        self, *, event_id: str, error_text: str, retry_base_seconds: int, retry_max_seconds: int
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT delivery_attempt_count
                    FROM thread_events
                    WHERE event_id = $1
                    FOR UPDATE
                    """,
                    event_id,
                )
                if row is None:
                    return
                next_attempt_count = int(row["delivery_attempt_count"] or 0) + 1
                delay_seconds = min(
                    retry_max_seconds, retry_base_seconds * (2 ** min(next_attempt_count - 1, 10))
                )
                next_time = datetime.now(UTC) + timedelta(seconds=delay_seconds)
                await conn.execute(
                    """
                    UPDATE thread_events
                    SET delivery_attempt_count = $1,
                        next_delivery_attempt_at = $2,
                        last_delivery_error = $3
                    WHERE event_id = $4
                    """,
                    next_attempt_count,
                    next_time,
                    error_text[:4000],
                    event_id,
                )

    async def cancel_pending_events_for_thread(self, *, thread_id: str, reason: str) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            status_text = await conn.execute(
                """
                UPDATE thread_events
                SET pending_delivery = FALSE,
                    next_delivery_attempt_at = NULL,
                    last_delivery_error = COALESCE(last_delivery_error, $1)
                WHERE thread_id = $2 AND pending_delivery = TRUE
                """,
                reason[:4000],
                thread_id,
            )
        return _rowcount_from_status(status_text)

    async def update_thread_terminal_status(
        self, *, thread_id: str, status: str
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE threads
                SET status = $1,
                    terminal_at = COALESCE(terminal_at, NOW()),
                    updated_at = NOW()
                WHERE thread_id = $2 AND status NOT IN ('done', 'closed')
                RETURNING *
                """,
                status,
                thread_id,
            )
        if row is not None:
            return _row_to_dict(row)
        return await self.get_thread(thread_id)

    async def list_inactivity_candidates(
        self, *, timeout_seconds: int, limit: int
    ) -> list[dict[str, Any]]:
        assert self.pool is not None
        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM threads
                WHERE status NOT IN ('done', 'closed')
                  AND last_message_sender_agent_slug IS NOT NULL
                  AND last_activity_at IS NOT NULL
                  AND last_activity_at <= $1
                  AND (
                        last_inactivity_event_at IS NULL
                        OR last_inactivity_event_at <= $1
                  )
                ORDER BY last_activity_at ASC
                LIMIT $2
                """,
                cutoff,
                max(1, limit),
            )
        return [_row_to_dict(row) for row in rows if row is not None]

    async def mark_inactivity_sent(self, *, thread_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET last_inactivity_event_at = NOW(), updated_at = NOW()
                WHERE thread_id = $1
                """,
                thread_id,
            )

    async def is_agent_online(self, *, agent_slug: str, lease_seconds: int) -> bool:
        agent = await self.get_agent(agent_slug)
        if agent is None:
            return False
        return self.timestamp_within_lease(agent.get("last_seen_at"), lease_seconds=lease_seconds)
