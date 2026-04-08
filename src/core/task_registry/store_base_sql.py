from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _CodecConnection(Protocol):
    async def set_type_codec(
        self,
        typename: str,
        *,
        schema: str,
        encoder: object,
        decoder: object,
        format: str = ...,
    ) -> None: ...


def quote_ident(identifier: str) -> str:
    if not SCHEMA_NAME_RE.match(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


async def init_connection(conn: _CodecConnection) -> None:
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
